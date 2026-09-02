"""WP6: the surf dashboard is registered on every surface that must agree.

CLAUDE.md's "Hiding a dashboard touches five surfaces and they must agree"
note applies in reverse to *adding* one: ``GAMES`` in
``screens/game_select.py``, the manager/screen wiring and ``_GAME_CYCLE`` in
``app.py``, the ``--game`` choices in ``__main__.py``, the CLAUDE.md dashboard
table and the README.  A dashboard registered on four of the five is worse
than one registered on none: it half-works.

Every assertion below is derived from ``GAMES`` wherever it can be, so a later
hide, show or reorder *moves* these tests instead of breaking them -- the
mistake the hardcoded ``bakery`` assertions made before they were rewritten.

Zero network: managers are replaced by stubs before ``run_test()``, and the CLI
is driven with ``MaxPaneApp`` swapped for a recorder, exactly the way
``tests/test_cli_game_choices.py`` and ``tests/test_app_startup.py`` do it.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen

REPO = Path(__file__).resolve().parents[1]

#: The one menu row this WP adds, asserted verbatim so the copy cannot drift.
#: The key was "7" until 2026-08-10, when surf was moved to the top of the
#: menu; the row is still pinned verbatim because the *copy* is what must not
#: drift, and the key is part of what a user reads off the screen.
SURF_ROW = (
    "1",
    "surf",
    "Surfboard",
    "The onchain adventures of surfsurf.eth",
)

#: Attribute names of every manager ``MaxPaneApp.__init__`` builds.  Hardcoded
#: on purpose: the failure this guards is a manager that was *never built*, and
#: a list derived from the app could not see that.
MANAGER_ATTRS = [
    "_bakery_manager",
    "_frenpet_manager",
    "_frenpet_full_manager",
    "_frenpet_wallet_manager",
    "_frenpet_perf_manager",
    "_base_manager",
    "_cattown_manager",
    "_ocm_manager",
    "_dota_manager",
    "_ttt_manager",
    "_talismans_manager",
    "_fwa_manager",
    "_surf_manager",
    "_curator_manager",
]


class CountingManager:
    """Manager that records fetches and closes.  Never touches the network."""

    def __init__(self) -> None:
        self._error_count = 0
        self.calls = 0
        self.closed = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        return {}

    async def close(self) -> None:
        self.closed += 1


def _stubbed_app(initial_game: str = "base") -> tuple[MaxPaneApp, dict[str, CountingManager]]:
    """The real app with every manager replaced by a stub."""
    app = MaxPaneApp(initial_game=initial_game)
    stubs: dict[str, CountingManager] = {}
    for attr in MANAGER_ATTRS:
        stub = CountingManager()
        stubs[attr] = stub
        setattr(app, attr, stub)
    return app, stubs


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see.

    Reaching into the compositor is the only way to prove a line is *on
    screen* rather than merely present in a widget's content.
    """
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


# ---------------------------------------------------------------------------
# app.py: the manager
# ---------------------------------------------------------------------------


def test_every_manager_attribute_exists_on_a_fresh_app() -> None:
    """``__init__`` builds every manager, surf included."""
    app = MaxPaneApp()
    for attr in MANAGER_ATTRS:
        assert getattr(app, attr, None) is not None, f"{attr} was never built"


def test_surf_manager_takes_the_poll_interval() -> None:
    """The app hands its poll interval to SurfManager like every other game."""
    from maxpane_dashboard.data.surf_manager import SurfManager

    app = MaxPaneApp(poll_interval=45)
    assert isinstance(app._surf_manager, SurfManager)


def test_surf_has_a_prefetch_manager() -> None:
    """No --game choice may fall through the prefetch map silently."""
    app = MaxPaneApp()
    assert app._prefetch_manager("surf") is app._surf_manager


def test_quit_closes_the_surf_manager() -> None:
    """``q`` must await ``SurfManager.close()`` -- cache saved, client closed.

    Goes through the menu quit path (``space`` dismisses the splash, ``q`` on
    the menu bubbles to the app binding), which is the path LOW-19 fixed and
    the one a user reaches with ``m`` then ``q``.
    """

    async def _run() -> None:
        app, stubs = _stubbed_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press("q")
            await pilot.pause()

        assert stubs["_surf_manager"].closed == 1, (
            "SurfManager.close() ran "
            f"{stubs['_surf_manager'].closed} times on quit; the surf cache is "
            "not persisted and its httpx client is abandoned"
        )
        for attr, stub in stubs.items():
            assert stub.closed == 1, f"{attr} closed {stub.closed} times"
        assert app._exception is None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# app.py: the screen and the tab cycle
# ---------------------------------------------------------------------------


def test_launching_surf_installs_the_surf_screen() -> None:
    """``_launch_game('surf')`` must reach a SurfScreen, not the else-return.

    Driven through ``_launch_game`` rather than the menu because the menu row
    lands two tasks later; the branch is what is under test here.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game("surf", first=True)
            await pilot.pause()

            assert isinstance(app.screen, SurfScreen), (
                f"_launch_game('surf') left {type(app.screen).__name__} on "
                "screen -- the branch is missing and it hit `else: return`"
            )
            assert app.screen.name == "surf"
            assert app.is_screen_installed("surf")
            assert app._exception is None

    asyncio.run(_run())


def test_launching_surf_twice_reuses_one_installed_screen() -> None:
    """The install is guarded, so ``m`` -> surf -> ``m`` -> surf leaks nothing."""

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game("surf", first=True)
            await pilot.pause()
            installed = len(app._installed_screens)
            for _ in range(5):
                app._launch_game("surf")
                await pilot.pause()
            assert len(app._installed_screens) == installed
            assert app._exception is None

    asyncio.run(_run())


def test_surf_is_in_the_tab_cycle_exactly_once() -> None:
    """Tab must reach surf, and must not visit it twice per lap."""
    assert MaxPaneApp._GAME_CYCLE.count("surf") == 1, MaxPaneApp._GAME_CYCLE


def test_tab_from_the_previous_game_reaches_surf() -> None:
    """The cycle is walked for real, not re-declared.

    ``_launch_game`` is replaced by a recorder so no second dashboard mounts
    (which would start a real poll timer).
    """
    cycle = MaxPaneApp._GAME_CYCLE
    previous = cycle[cycle.index("surf") - 1]

    async def _run() -> None:
        app, _stubs = _stubbed_app(previous)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game(previous, first=True)
            await pilot.pause()
            app._current_game = previous

            launched: list[str] = []
            app._launch_game = lambda game_id, **kw: launched.append(game_id)

            await pilot.press("tab")
            await pilot.pause()

            assert launched == ["surf"], (
                f"tab from {previous} went to {launched} instead of surf"
            )
            assert app._current_game == "surf"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# __main__.py: the --game choice
# ---------------------------------------------------------------------------


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, returning the app's kwargs.

    No TUI is started, no terminal is resized, and ``logging.basicConfig`` is
    neutered so a test run never truncates ``~/.maxpane/maxpane.log``.
    """
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli, "_maximize_terminal", lambda *a, **k: None)
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


def test_game_surf_is_accepted(monkeypatch) -> None:
    captured = _run_cli(monkeypatch, ["--game", "surf"])
    assert captured["initial_game"] == "surf"
    assert captured.get("ran") is True


def test_the_default_game_is_the_first_menu_entry(monkeypatch) -> None:
    """The prefetched dashboard is the one the menu opens on.

    This pinned ``fwa`` by name until 2026-08-10, when surf took position 1 and
    the default followed it.  Naming the winner again would only re-pin a
    literal; what actually breaks launch is the two surfaces *disagreeing* --
    the menu offering one dashboard first while ``--game``'s default warms
    another's data -- so that is what is asserted, derived from ``GAMES``.
    """
    captured = _run_cli(monkeypatch, [])
    assert captured["initial_game"] == GAMES[0][1]
    # ...and the concrete value the user asked for.  This line is *not* the
    # anti-vacuity guard it was once commented as: an emptied ``GAMES`` makes
    # the assert above raise ``IndexError`` rather than pass, and a ``main()``
    # that ignored ``args.game`` and hardcoded ``"surf"`` leaves both asserts
    # green (that mutation is caught by
    # ``test_cli_game_choices.py::test_reachable_games_still_work``, which
    # drives every ``--game`` value rather than only the default).  What it
    # does do is pin the settled decision -- surf first -- the same way
    # ``SURF_ROW`` above pins the row verbatim: a *coordinated* reorder of both
    # surfaces would otherwise pass silently.  Change it deliberately, with the
    # order, or not at all.
    assert captured["initial_game"] == "surf"


def test_a_typo_is_still_rejected(monkeypatch) -> None:
    """The choices list stays a whitelist -- ``--game surfs`` must exit 2."""
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--game", "surfs"])


# ---------------------------------------------------------------------------
# game_select.py: the menu row -- the surface a user actually presses
# ---------------------------------------------------------------------------


def test_surf_is_menu_entry_one() -> None:
    """The row is asserted verbatim so the copy cannot drift silently."""
    row = next((g for g in GAMES if g[1] == "surf"), None)
    assert row is not None, "surf is not registered in GAMES"
    assert tuple(row) == SURF_ROW, f"menu row drifted: {row}"


def test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order() -> None:
    """Two orderings of one list are one bug waiting to happen.

    ``_GAME_CYCLE`` and ``GAMES`` are separate literals in separate files;
    this is the assertion that keeps them in step, and it is derived from
    both rather than restating either.
    """
    assert MaxPaneApp._GAME_CYCLE == [game_id for _key, game_id, *_ in GAMES]


def test_the_cli_choices_are_exactly_the_menu(monkeypatch) -> None:
    """CLI -> menu, the direction ``test_cli_game_choices`` does not assert.

    It checks that every menu entry is an accepted choice; this checks that
    every accepted choice is a menu entry, in order.  Together they pin the
    two lists to each other.
    """
    import argparse

    seen: dict[str, list[str]] = {}
    real_add_argument = argparse.ArgumentParser.add_argument

    def spy(self, *args, **kwargs):
        if args and args[0] == "--game":
            seen["choices"] = list(kwargs.get("choices") or [])
        return real_add_argument(self, *args, **kwargs)

    monkeypatch.setattr(argparse.ArgumentParser, "add_argument", spy)
    _run_cli(monkeypatch, [])

    assert seen["choices"] == [game_id for _key, game_id, *_ in GAMES]


def test_pressing_the_surf_key_opens_the_surf_dashboard() -> None:
    """The whole path: splash -> menu -> the key the row advertises.

    The key is read out of ``GAMES`` rather than typed, so the 2026-08-10
    reorder that took surf from "7" to "1" moved this test with the menu
    instead of breaking it -- only the name had to change.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press(key)
            await pilot.pause()

            assert isinstance(app.screen, SurfScreen)
            assert app.screen.name == "surf"
            assert app._exception is None
        assert app.return_code != 1

    asyncio.run(_run())


def test_the_menu_lists_the_surf_row() -> None:
    """The row reaches the compositor -- not merely the GAMES list.

    Asserted on **one composited line**, not as three independent substrings
    of the whole screen.  The loose version searched the full text for
    ``"[7]"`` and for ``"Surfboard"`` separately, so it stayed green with the
    key on some *other* dashboard's row -- which is exactly the state the
    2026-08-10 reorder could have left behind.  What a user has to be able to
    do is read the key off the same line as the name.
    """

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            row = next(
                (l for l in _screen_text(app).splitlines() if SURF_ROW[2] in l), ""
            )
            assert row, f"{SURF_ROW[2]} never reached the compositor"
            assert f"[{SURF_ROW[0]}]" in row, (
                f"the Surfboard row renders as {row.strip()!r}, which does not "
                f"advertise the key [{SURF_ROW[0]}] that GAMES gives it"
            )
            assert "onchain adventures" in row  # from the description

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# themes/minimal.tcss: the shared stylesheet must know about surf
# ---------------------------------------------------------------------------

_TCSS = REPO / "maxpane_dashboard" / "themes" / "minimal.tcss"


def _surf_block() -> str:
    """The surf section of the shared stylesheet, or '' if absent."""
    text = _TCSS.read_text(encoding="utf-8")
    marker = "/* ── Surf screen"
    if marker not in text:
        return ""
    start = text.index(marker)
    nxt = text.find("/* ── ", start + len(marker))
    return text[start:] if nxt == -1 else text[start:nxt]


def test_the_shared_stylesheet_has_a_surf_block() -> None:
    """DEFAULT_CSS is a fallback; the app stylesheet is what actually renders."""
    block = _surf_block()
    assert block, (
        "themes/minimal.tcss has no surf block -- SurfScreen's proportions "
        "come from DEFAULT_CSS only, which any theme edit to the shared ids "
        "(#middle-row, #bottom-row, #separator) can silently override"
    )
    for selector in (
        "SurfScreen #hero-row",
        "SurfScreen #middle-row",
        "SurfScreen #surf-right-rail",
        "SurfScreen #bottom-row",
        "SurfHero",
        "SurfSignals",
        "SurfFeed",
        "SurfDevActivity",
        "SurfMarket",
        "SurfNft",
    ):
        assert selector in block, f"{selector} is not styled in the surf block"


def test_the_surf_hero_row_has_no_vertical_padding() -> None:
    """The FWA coverage-badge lesson, applied before it can bite.

    ``#hero-row`` is ``height: auto`` around a seven-row SurfHero whose boxes
    hold five content lines inside a seven-row frame.  A vertical pad here
    pushes the boxes' bottom border off the row -- exactly the way
    ``padding: 1 2`` clipped the FWA coverage badge -- and, against ``auto``,
    silently pads the whole row back out to the dead height this layout was
    restructured to remove.  Horizontal padding (``0 1``, ``0 2``) is fine.
    """
    import re

    block = _surf_block()
    hero = re.search(r"SurfScreen #hero-row\s*\{([^}]*)\}", block)
    assert hero, "no SurfScreen #hero-row rule in the surf block"
    for line in hero.group(1).splitlines():
        line = line.strip()
        if line.startswith("padding:"):
            vertical = line.split(":", 1)[1].strip().rstrip(";").split()[0]
            assert vertical == "0", (
                f"vertical padding {vertical!r} on #hero-row will clip the "
                "hero boxes and re-inflate the row"
            )


# -- the two copies of the surf structure must agree --------------------
#
# ``SurfScreen.DEFAULT_CSS`` and the surf block restate the same layout: the
# block is what renders (an app stylesheet outranks DEFAULT_CSS), DEFAULT_CSS
# is what keeps the screen correctly proportioned under a theme that has no
# surf rules. Edit one and not the other and the dashboard has two different
# layouts depending on which stylesheet is loaded -- and the tests that use
# ``_ThemedHarness`` would certify only one of them.

#: Shorthand properties whose absence means "the CSS default", so that one
#: copy spelling ``padding: 0 0`` and the other omitting it is agreement.
_SHORTHAND_DEFAULTS = {"padding": "0", "margin": "0"}

#: What this comparison is about: the geometry. Colour and text properties
#: belong to the theme and to the widgets' own DEFAULT_CSS.
#:
#: ``min-height`` joined the list with the three-row layout: it is the floor
#: under ``SurfDevActivity`` in the right rail, and it is load-bearing rather
#: than decorative -- a ``1fr`` child of a scroll container shrinks instead of
#: overflowing, so the floor is the only thing that turns "the rail is too
#: short" into the overflow the title bar's ``‹ taller`` is built on. One copy
#: carrying it and the other not would mean the marker fires under one
#: stylesheet and never under the other.
#: ``scrollbar-size`` joined 2026-08-24 (fix round 2). It is geometry, not
#: decoration: the Textual default is two cells wide, so a copy that drops
#: the ``1 1`` hands a scroll container's children one column less than the
#: other copy does. Both rails on this screen (``#surf-right-rail`` and the
#: launchpad's ``#surf-launchpad-rail``) declare it in both copies, and
#: nothing else on the screen declares it at all -- absent from both sides is
#: agreement, so adding it here costs the other selectors nothing. It was the
#: last scroll property in either stylesheet that no test in the repo
#: compared.
_STRUCTURAL = (
    "width", "height", "min-height", "padding", "margin", "scrollbar-size",
)

#: The two copies deliberately do **not** cover the same selector set, and
#: both asymmetries are load-bearing:
#:
#: * ``#title-bar`` / ``#separator`` are DEFAULT_CSS-only. The shared
#:   stylesheet already styles those two ids for every screen (lines 12-130);
#:   the surf block restating them would give a shared rule a second owner.
#: * The feed's ``> #surf-feed-body`` rule and the activity panel's
#:   ``> RichLog`` rule are block-only: they are the app-stylesheet half of
#:   the feed/activity height, and the widgets' own DEFAULT_CSS owns the rest.
#:   They were one shared selector until the feed swapped its ``RichLog`` for
#:   a scroll container of per-row click targets; keeping the set spelled out
#:   in full is what turns a future re-fold of the two back into one selector
#:   -- which would silently stop matching one of the panes -- into a failure
#:   here rather than a layout that quietly sizes to its content.
#:
#: Pinned as *sets*, not counted. A count is the vacuity hole it was meant to
#: close: the guard used to read ``len(shared) >= 8`` against a real overlap
#: of ten, so renaming ``SurfMarket`` to ``SurfMarketX`` in DEFAULT_CSS alone
#: dropped the market out of the comparison entirely and left nine -- still
#: green, with the two copies' market geometry never compared again.
_DEFAULT_CSS_ONLY = frozenset({"#title-bar", "#separator"})
_BLOCK_ONLY = frozenset({"SurfFeed > #surf-feed-body", "SurfDevActivity > RichLog"})


def _expand(value: str) -> tuple[str, ...]:
    """CSS box shorthand -> four values, so ``0 0`` == ``0`` == ``0 0 0 0``."""
    parts = value.split()
    if len(parts) == 1:
        return tuple(parts * 4)
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    return tuple(parts[:4])


def _rules(css: str) -> dict[str, dict[str, str]]:
    """``{selector: {property: value}}`` for the structural properties.

    A leading ``SurfScreen `` is stripped: DEFAULT_CSS has to scope every
    rule to the screen, the block scopes the *ids* (the shared ``#middle-row``
    / ``#bottom-row`` rules above it are law for nine other screens) and
    leaves the ``Surf*`` types unscoped, since those types exist nowhere
    else. The two spellings mean the same thing here.
    """
    import re

    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[str, dict[str, str]] = {}
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        head, body = chunk.split("{", 1)
        props = {}
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            name, _, value = decl.partition(":")
            name = name.strip()
            if name in _STRUCTURAL:
                props[name] = " ".join(value.split())
        if not props:
            continue
        for selector in head.split(","):
            selector = " ".join(selector.split())
            if selector.startswith("SurfScreen "):
                selector = selector[len("SurfScreen "):]
            out.setdefault(selector, {}).update(props)
    return out


def test_the_stylesheet_block_and_default_css_describe_one_layout() -> None:
    """Every rule the two copies share must carry the same geometry."""
    from maxpane_dashboard.screens.surf import SurfScreen

    fallback = _rules(SurfScreen.DEFAULT_CSS)
    block = _rules(_surf_block())

    # Guard against the comparison quietly becoming vacuous. A renamed or
    # deleted selector on one side does not shrink a threshold here -- it
    # lands in one of these two differences and fails by name.
    assert set(fallback) - set(block) == _DEFAULT_CSS_ONLY, (
        "DEFAULT_CSS has selectors the surf block does not: "
        f"{sorted((set(fallback) - set(block)) - _DEFAULT_CSS_ONLY)} -- each "
        "is a rule the two copies no longer compare"
    )
    assert set(block) - set(fallback) == _BLOCK_ONLY, (
        "the surf block has selectors DEFAULT_CSS does not: "
        f"{sorted((set(block) - set(fallback)) - _BLOCK_ONLY)}"
    )
    shared = sorted(set(fallback) & set(block))

    for selector in shared:
        for prop in _STRUCTURAL:
            default = _SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _SHORTHAND_DEFAULTS:
                assert _expand(left) == _expand(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


def test_the_activity_floor_is_the_same_number_in_both_stylesheets() -> None:
    """Three copies of one number: the constant and both stylesheets.

    ``screens/surf.ACTIVITY_MIN_HEIGHT`` documents the floor and the module
    docstring reasons from it, but CSS cannot read a Python constant, so both
    stylesheets restate it as a literal. Drift is invisible until a short
    terminal renders: the marker would light at one height and the panel thin
    out at another.
    """
    from maxpane_dashboard.screens.surf import ACTIVITY_MIN_HEIGHT, SurfScreen

    for name, css in (
        ("DEFAULT_CSS", SurfScreen.DEFAULT_CSS),
        ("minimal.tcss", _surf_block()),
    ):
        declared = _rules(css)["SurfDevActivity"].get("min-height")
        assert declared == str(ACTIVITY_MIN_HEIGHT), (
            f"{name} floors SurfDevActivity at {declared!r} while "
            f"ACTIVITY_MIN_HEIGHT is {ACTIVITY_MIN_HEIGHT}"
        )
        # ...and it is a floor under a `1fr`, not a fixed height: a fixed one
        # would stop the panel absorbing the rail's spare rows.
        assert _rules(css)["SurfDevActivity"]["height"] == "1fr", name


def test_the_middle_row_is_the_only_one_that_grows() -> None:
    """The dead-space fix, pinned in both copies of the stylesheet.

    Give ``#bottom-row`` a ``1fr`` back and a tall terminal splits its spare
    rows between the feed and eight lines of NFT panel, which is the empty
    fifth of the screen this layout replaced.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    for name, css in (
        ("DEFAULT_CSS", SurfScreen.DEFAULT_CSS),
        ("minimal.tcss", _surf_block()),
    ):
        rules = _rules(css)
        # The screen's own rows -- ``#surf-right-rail`` is a column *inside*
        # the middle row and legitimately takes that row's height.
        rows = ("#hero-row", "#middle-row", "#bottom-row")
        growing = [r for r in rows if rules[r].get("height") == "1fr"]
        assert growing == ["#middle-row"], (
            f"{name}: rows that absorb slack are {growing}, expected "
            "#middle-row alone"
        )
        assert rules["#hero-row"]["height"] == "auto", name
        assert rules["#bottom-row"]["height"] == "auto", name


def test_all_six_detectors_survive_the_real_stylesheet() -> None:
    """Composited proof, under ``minimal.tcss``, at the pinned width.

    This is a regression guard rather than the driver for the block: it also
    passes with DEFAULT_CSS alone today.  It is what turns red if a future
    theme edit -- or a "tidy" of the block above -- costs the screen a row.

    The panel now carries ten detectors, not six, and ``_FakeManager()``'s
    default fixture (``lp``/``gate``/``deploy``/``burn``/``thread`` all
    ``ok``) exercises quiet-collapse: those five fold into one ``· 5 quiet``
    line rather than keeping their own -- see ``widgets/surf/signals.py``'s
    Quiet-collapse section. ``decoy``/``burnready``/``hot`` are absent from
    that fixture, so they read as unknown and -- unlike ``ok`` -- never fold,
    which is what keeps them each individually visible below.

    NEW REPLY (2026-08-24) is the fifth quiet row and never appears by name
    here, which is the correct outcome and worth saying out loud: a detector
    that is ``ok`` is supposed to disappear into the count. It has its own
    named assertion in ``tests/widgets/test_surf_widgets_a.py``, under the
    FIRED state where the reader is meant to see it.
    """
    from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS

    harness = _surf_screen_harness()

    async def _run() -> None:
        screen = harness.SurfScreen(
            harness._FakeManager(), poll_interval=30, name="surf"
        )
        app = harness._ThemedHarness(screen)
        async with app.run_test(size=(SURF_FULL_LAYOUT_COLUMNS, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            text = harness._screen_text(app)
            for label in (
                "NEW POST",
                "BRIDGE STAGE",
                "DECOY POOL",
                "BURN READY",
                "HOT COIN",
            ):
                assert label in text, f"{label} never reached the compositor"
            assert "5 quiet" in text, (
                "lp/gate/deploy/burn/thread are all ok in this fixture and "
                "should fold into one quiet line"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# __main__.FULL_LAYOUT_COLUMNS must cover every dashboard, surf included
# ---------------------------------------------------------------------------


def test_all_five_pool4_panels_survive_the_real_stylesheet() -> None:
    """Every ``p`` panel reaches the compositor through the REAL app.

    ``test_all_six_detectors_survive_the_real_stylesheet`` above is the
    precedent and the reason: a panel can be composed, dispatched and
    correct in a bare harness and still reach no pixel once the shared
    stylesheet has its say, because the app stylesheet outranks
    ``SurfScreen.DEFAULT_CSS`` and this file is where the two meet. The
    launchpad rail shipped a version of exactly that -- a body written into
    ``DEFAULT_CSS`` alone with ``minimal.tcss`` still putting the panels
    somewhere else -- and only an app-level test noticed.

    So this goes through the splash and the game-select menu like a user
    does, at the pinned layout size, and asks for each panel's own **title**
    rather than for a value: a title is the one string a panel renders in
    every state, so the assertion cannot be satisfied by a lucky number and
    cannot fail merely because a payload changed.
    """
    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        from maxpane_dashboard.screens.surf import (
            SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS,
        )

        app = _offline_app(DeadSourcesManager())
        size = (SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            before = _screen_text(app)
            await pilot.press("p")
            await pilot.pause()
            text = _screen_text(app)

        titles = ("HATCHES", "POOL4 FLOW", "THE SPLIT", "THE RATCHET",
                  "sIMD VAULT")
        for title in titles:
            assert title in text, (
                f"{title} reaches no pixel through the real stylesheet"
            )
        # The premise, and it has to be this one rather than `before !=
        # text`. Mutating `_show_mode` so it never sets the pool4 body's
        # `display` leaves the body visible from the moment it is composed
        # -- so all five titles are on screen before `p` is pressed, the
        # screen still changes when `p` hides the dashboard rows, and a
        # "something changed" premise stays green through a body that was
        # never hidden in the first place. Proven: that mutation left the
        # earlier version of this test passing.
        #
        # The claim is that the body is composed HIDDEN and `p` is what
        # shows it, so that is what is asserted -- absent before, present
        # after, per title.
        for title in titles:
            assert title not in before, (
                f"{title} is on screen before `p` was pressed -- the pool4 "
                "body is not being composed hidden, so the swap this test "
                "claims to exercise is not happening"
            )
        # ...and at the body's own pinned height nothing is scrolled off, so
        # this is the whole body rather than as much of it as fits.
        from maxpane_dashboard.screens.surf import TALLER_HINT

        assert TALLER_HINT not in text, (
            "the body does not fit at its own pinned height -- either the "
            "pin is wrong or a panel grew"
        )

    asyncio.run(_run())


def test_the_documented_width_covers_surf() -> None:
    """``--font-size`` help quotes this number; it must not become a lie."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
    from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS

    assert FULL_LAYOUT_COLUMNS >= SURF_FULL_LAYOUT_COLUMNS, (
        f"surf needs {SURF_FULL_LAYOUT_COLUMNS} columns, the app documents "
        f"{FULL_LAYOUT_COLUMNS}: raise FULL_LAYOUT_COLUMNS and the README "
        "width table together"
    )


def test_the_readme_quotes_the_documented_width() -> None:
    """The README's width table is prose around one number; pin them together."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"≥ {FULL_LAYOUT_COLUMNS}" in readme, (
        f"README's width table never mentions ≥ {FULL_LAYOUT_COLUMNS}"
    )


def _surf_screen_harness():
    """The screen test module, loaded as a library (it owns the fixtures)."""
    import importlib.util

    path = REPO / "tests" / "screens" / "test_surf_screen.py"
    spec = importlib.util.spec_from_file_location("_surf_screen_harness", path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    return harness


#: Every document that tells a reader ``FULL_LAYOUT_COLUMNS`` clears the
#: markers, and must therefore carry the linked-post caveat that makes that
#: true.  **This list follows the documentation, not the other way round.**
#: ``CLAUDE.md`` was on it until 2026-08-26, when the layout rules moved out of
#: that file into the ``terminal-layout`` skill; it now only names the constant
#: and points at the skill, so it makes no claim that needs the caveat, and the
#: skill inherited both.  If a fourth document starts documenting the width, add
#: it here -- an unlisted document is one this test cannot keep honest.
_DOCS_THAT_DOCUMENT_THE_WIDTH = (
    "README.md",
    ".claude/skills/terminal-layout/SKILL.md",
)


def test_the_documented_width_is_not_promised_to_clear_every_post() -> None:
    """The width table says "nothing" of the *layout*, and must not overpromise.

    Measured here, not assumed: against the **full** captured feed -- the one
    that includes the nonce-13 post whose tx link is a single unbreakable
    91-column token -- surf still lights a ``‹ widen`` at
    ``FULL_LAYOUT_COLUMNS``.  A README row reading "nothing" with no caveat is
    therefore false on the exact terminal it tells people to build, and the
    caveat is what makes it true.

    Bound in both directions on purpose.  If a future change ever does clear
    that marker at the documented width, this test fails on the *first*
    assertion and tells you to delete the caveat rather than leave two
    user-facing documents warning about something that no longer happens.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    harness = _surf_screen_harness()
    lit = asyncio.run(
        harness._widen_markers(
            FULL_LAYOUT_COLUMNS, payload=harness._frozen_payload()
        )
    )
    assert lit > 0, (
        f"the full captured feed now clears every marker at {FULL_LAYOUT_COLUMNS} "
        "columns -- delete the linked-post caveat from README.md and CLAUDE.md "
        "instead of leaving them warning about nothing"
    )

    for name in _DOCS_THAT_DOCUMENT_THE_WIDTH:
        text = (REPO / name).read_text(encoding="utf-8")
        assert "links a transaction" in text, (
            f"{name} documents {FULL_LAYOUT_COLUMNS} columns as clearing every "
            "marker, which a post linking a transaction makes false"
        )


#: The README width table names panels by their on-screen titles; this maps
#: each back to the widget whose rectangle the marker has to be in.  Spelled
#: out rather than derived from the widgets, because the *titles* are what a
#: reader matches against and a renamed panel must redden here.
_README_PANEL_TITLES = {
    "ANNOUNCE FEED": "SurfFeed",
    "DEV ACTIVITY": "SurfDevActivity",
    "IMD MARKET": "SurfMarket",
    "IDENTITY.MD": "SurfNft",
    "SIGNALS": "SurfSignals",
}


def _readme_width_bands() -> list[tuple[tuple[int, ...], frozenset[str]]]:
    """``(widths to check, surf panels the row names)`` per width-table row.

    Parsed out of the README rather than restated here: the table is the
    artefact under test, and a copy of it in this file would be one more
    surface to drift.
    """
    lines = (REPO / "README.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("| columns |"))
    bands = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        widths = tuple(int(n) for n in re.findall(r"\d+", cells[0]))
        titles = re.findall(r"surf `([A-Z][A-Z .]*?) ‹ widen", cells[1])
        bands.append((widths, frozenset(_README_PANEL_TITLES[t] for t in titles)))
    assert bands, "the README width table did not parse -- did its shape change?"
    return bands


def test_the_readme_width_table_names_the_panels_that_are_really_lit() -> None:
    """Every row of the table, rendered.  Nothing pinned the *contents* before.

    The number at the bottom of the table was pinned from the day it was
    written; which panels each band lists was not, so the rows went stale in
    place -- for two days the table named no ``IMD MARKET`` at all while that
    panel was the one lighting a marker in every band, and it put 135-141 in
    one row when the feed and the market go out one column apart.

    Both ends of each band are rendered, so a band that has silently split
    fails rather than passing on its first column.
    """
    harness = _surf_screen_harness()
    for widths, expected in _readme_width_bands():
        for width in {widths[0], widths[-1]}:
            lit = asyncio.run(harness._panels_asking_for_width(width))
            assert lit == set(expected), (
                f"at {width} columns the README says {sorted(expected)} and the "
                f"screen lights {sorted(lit)}"
            )


#: Every surface that narrates the 3:2 -> 7:6 re-seam.  All three carried the
#: same sentence, so all three carried the same lie.
_SEAM_NARRATIVE_SURFACES = (
    "CLAUDE.md",
    "README.md",
    "maxpane_dashboard/__main__.py",
)

#: The band where the 7:6 seam cost the announce feed its wrapped-post
#: rendering before ``feed.FULL_TEXT_WIDTH`` came down 76 -> 71.  Kept as a
#: *forbidden* string now: the band is closed, so a document still naming it
#: is telling a reader about a limitation that no longer exists.
_CLOSED_FEED_REGRESSION_BAND = "135–150"

#: Sentences that say the re-seam was free *everywhere*.  Each was true of the
#: layout and false of the feed, and each is what final review flagged.
#:
#: Still forbidden after the threshold fix, and this is the subtle part: the
#: fix moved the feed's wrap edge to 142, but the old 3:2 seam wrapped from
#: **135**.  So a 135-141 band survives where the previous layout wrapped and
#: this one does not -- narrower than before and no longer worth naming in a
#: width table, but "nothing was given up" is still not a true sentence.
_UNQUALIFIED_FREE_CLAIMS = (
    "bought nothing",
    "without a widget giving anything up",
    "without a widget losing anything",
    "Nothing was hidden, shortened or re-cut",
    "Nothing was re-cut or hidden",
    "Nothing was hidden or cut to get there",
)


def test_the_docs_describe_the_feed_regression_as_closed() -> None:
    """The 7:6 seam cost the feed a tier; lowering its own threshold fixed it.

    This test replaces one that held the docs to naming a 135-150 band where
    the feed printed one truncated line per post.  That band is closed --
    ``feed.FULL_TEXT_WIDTH`` came down 76 -> 71, so the feed wraps from 142 --
    and the old test said, in its own failure message, to drop the qualifier
    rather than leave three documents hedging something that stopped
    happening.  This is that drop, with the direction reversed: the band is
    now a *forbidden* string, because a document naming it describes a
    limitation a reader will not meet.

    The width it asserts is **measured on the real screen**, not read from
    ``feed.FULL_TEXT_WIDTH``.  Deriving it from the constant would make the
    docs agree with themselves through any regression at all.
    """
    harness = _surf_screen_harness()
    full = harness.MEASURED_FULL_LAYOUT_COLUMNS
    feed_edge = harness.MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL

    # The feed is now the *last* panel asking for width, so the screen's full
    # width simply is its wrap edge. This used to sweep the band above the
    # edge asserting every marker in it was the activity rail's; that band is
    # empty now (the rail clears from a 135-column terminal, seven columns
    # below), and a sweep over an empty band proves nothing, so the identity
    # is asserted instead.
    assert full == feed_edge, (
        f"the screen clears at {full} but the feed's own edge is {feed_edge}: "
        "some panel is buying width above the feed again, and the docs below "
        "claim none does"
    )
    assert asyncio.run(harness._widen_markers(full)) == 0
    # ...and one column below it the feed is shedding again: the number the
    # docs quote is the real edge, not a round one.
    assert asyncio.run(harness._markers_outside_the_activity_panel(feed_edge - 1)) > 0
    # ...and it is the *only* thing shedding there, i.e. the activity rail --
    # which set this width until its row shrank -- is already clean.
    assert asyncio.run(harness._widen_markers(feed_edge - 1)) == 1

    for name in _SEAM_NARRATIVE_SURFACES:
        text = (REPO / name).read_text(encoding="utf-8")
        for claim in _UNQUALIFIED_FREE_CLAIMS:
            assert claim not in text, (
                f"{name} says {claim!r} of the 3:2 -> 7:6 re-seam. The feed's "
                "wrap edge came back to 142, but the old seam wrapped from "
                "135, so a 135-141 band survives where this layout truncates "
                "and the old one did not"
            )
        assert _CLOSED_FEED_REGRESSION_BAND not in text, (
            f"{name} still names the {_CLOSED_FEED_REGRESSION_BAND} band where "
            "the announce feed printed one truncated line per post. That band "
            f"closed when FULL_TEXT_WIDTH fell to wrap from {feed_edge}"
        )
        assert str(feed_edge) in text, (
            f"{name} narrates the seam without naming {feed_edge}, the width "
            "the announce feed actually wraps from now"
        )


def test_the_readme_does_not_send_a_laptop_after_a_smaller_font() -> None:
    """The forced font already clears the full layout; the README said it did not.

    Derived, not written down: ``LAPTOP_COLUMNS_AT_THE_FORCED_FONT`` follows
    ``__main__._DEFAULT_FONT_SIZE``, so this asserts the real relationship
    between what the app forces and what the widest layout needs.  While the
    former covers the latter, telling a reader to pass a smaller
    ``--font-size`` to reach the full layout is false -- and the README said
    exactly that 46 lines above the sentence saying the opposite.  It was true
    for the width's 176 era and outlived it.

    If the width ever climbs back past what the forced font gives, the first
    assertion fails and the advice is required again.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    harness = _surf_screen_harness()
    laptop = harness.LAPTOP_COLUMNS_AT_THE_FORCED_FONT
    assert laptop >= FULL_LAYOUT_COLUMNS, (
        f"the forced font size gives {laptop} columns and the widest layout "
        f"needs {FULL_LAYOUT_COLUMNS}: the README's `--font-size` advice is "
        "required again, so put it back rather than deleting this test"
    )

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for claim in (
        "one tier short of the full layout",
        "reaching it means passing a smaller",
    ):
        assert claim not in readme, (
            f"README.md still says {claim!r} while {laptop} columns covers the "
            f"{FULL_LAYOUT_COLUMNS} the full layout needs"
        )
    # ...and it still says so positively, in one sentence carrying both numbers.
    assert any(
        str(FULL_LAYOUT_COLUMNS) in para and str(laptop) in para
        for para in readme.split("\n\n")
    ), (
        f"no README paragraph puts {FULL_LAYOUT_COLUMNS} and {laptop} together, "
        "which is the sentence that tells a reader they need no --font-size"
    )


#: The two docs read as the *current* spec for this dashboard.  The files under
#: ``docs/surf_work_packages/`` are deliberately excluded: they are build-time
#: records of what each work package was asked to do, and rewriting history
#: there would destroy the record rather than correct a lie.
_LIVE_SPEC_DOCS = ("surf_PRD.md", "surf_implementation_plan.md")


def test_the_live_spec_docs_describe_no_key_the_screen_does_not_bind() -> None:
    """The PRD and the plan are read as current, so they must stay current.

    Both described a ``c`` view swap after the binding, its action, the
    status-bar indicator and their tests were deleted -- the restructure that
    removed them updated the code, the README and CLAUDE.md and stopped at
    ``docs/``.  Derived from ``BINDINGS`` rather than asserting the absence of
    a literal, so re-adding the key legitimately would move this test instead
    of breaking it.

    The phrases below are the ones a *current* description uses (the slot-grid
    labels and the noun).  Prose recording that the swap was **removed** has to
    avoid them, which is the same trade
    ``test_no_theme_token_reaches_a_rich_parsing_surface`` makes: a scan of raw
    text cannot tell a specification from its own changelog.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    bound = {binding.key for binding in SurfScreen.BINDINGS}
    for name in _LIVE_SPEC_DOCS:
        text = (REPO / "docs" / name).read_text(encoding="utf-8")
        for phrase in ("`c` swap", "`c`-swap", "`c` A", "`c` B"):
            if phrase in text:
                assert "c" in bound, (
                    f"docs/{name} still describes {phrase!r}, and SurfScreen "
                    f"binds only {sorted(bound)}"
                )


# ---------------------------------------------------------------------------
# PRD §11.3: full outage renders explicit states, never a crash or a zero
# ---------------------------------------------------------------------------


class BoomManager:
    """Every fetch fails, the way an offline launch fails."""

    def __init__(self) -> None:
        self._error_count = 1
        self.calls = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        raise RuntimeError("no network")

    async def close(self) -> None:
        return None


class DeadSourcesManager:
    """Every source is down, but the contract is still honoured in full.

    ``degraded`` is built from the real :data:`SOURCES` tuple, not from
    hand-written names.  The vocabulary is PRD §5's "list[str] of source-group
    names" and the manager can only ever emit members of it -- a double that
    invents ``"state_rpc"``/``"blockscout"`` would still light the banner up
    while proving nothing about the strings the screen will actually receive,
    and would hide a ``_fmt_degraded`` bug that only bites on real group names.
    Importing the tuple also means a renamed group turns this test red instead
    of leaving it quietly testing a dead vocabulary.
    """

    def __init__(self) -> None:
        from maxpane_dashboard.data.surf_manager import SOURCES
        from maxpane_dashboard.data.surf_models import SURF_KEYS

        self._error_count = 1
        self.calls = 0
        self._keys = SURF_KEYS
        # `sorted` is the order the specified outage path emits (WP4's
        # `_cycle` sorts the collected group names); the outermost guard emits
        # `list(SOURCES)`. Same six names either way.
        self._degraded = sorted(SOURCES)

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        payload: dict[str, Any] = {key: None for key in self._keys}
        payload["degraded"] = list(self._degraded)
        return payload

    async def close(self) -> None:
        return None


def _offline_app(manager) -> MaxPaneApp:
    app, _stubs = _stubbed_app("surf")
    app._surf_manager = manager
    return app


@pytest.mark.parametrize("factory", [BoomManager, DeadSourcesManager])
def test_offline_launch_of_surf_never_kills_the_app(factory) -> None:
    """Splash -> menu -> surf's key with its manager down: degraded, not dead."""
    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        manager = factory()
        app = _offline_app(manager)
        async with app.run_test(size=(143, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()

            assert app.screen.name == "surf"
            assert app._exception is None, repr(app._exception)
            assert app.is_running
            assert manager.calls >= 1, "the screen never even tried to fetch"
        assert app.return_code != 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Fix round 1 (Important finding): the zero-catch above only proved
# ``imd_price_usd`` never fakes a zero. ``SURF_KEYS`` carries ~20 other
# numerics -- lp_liquidity, lp_imd, feed_nonce, supply, holders, transfers,
# identities-written -- and a future manager bug that zeroed any *one* of
# those instead would have passed the original test in silence. The house
# rule is "a failed read is None, never 0" (CLAUDE.md), not "the price is
# never a fake zero", so the assertion has to cover the numeric surface, not
# one representative field.
#
# Every ``SURF_KEYS`` entry is triaged into exactly one of three buckets
# below, and ``test_every_surf_key_is_triaged_for_the_zero_catch`` proves the
# triage is exhaustive by deriving its check from the live ``SURF_KEYS``
# tuple rather than a second hand-typed list -- a key added later fails that
# test instead of silently staying uncovered, which is the same defect this
# whole finding is about, one level up.
# ---------------------------------------------------------------------------

#: Keys whose type is never a bare ``int``/``float`` -- ``str``, ``bool`` or
#: ``list[...]`` -- so there is no None-vs-0 ambiguity to defend: a bool's
#: unread state is already distinct from ``False`` without going anywhere
#: near ``"0"``, and a list's unread state is ``None`` vs. ``[]``, the same
#: distinction ``surf_models.LogWindow``'s own docstring draws for ``()``.
_NON_NUMERIC_KEYS = frozenset(
    {
        "degraded", "feed_items",
        "sig_post_state", "sig_lp_state", "sig_gate_state",
        "sig_deploy_state", "sig_bridge_state", "sig_burn_state",
        "sig_post_detail", "sig_lp_detail", "sig_gate_detail",
        "sig_deploy_detail", "sig_bridge_detail", "sig_burn_detail",
        # NEW REPLY (2026-08-24), same two shapes as every row above it: a
        # state word and a detail string, neither of which has a numeric
        # zero to confuse with a failed read.
        "sig_thread_state", "sig_thread_detail",
        "lp_owner_ok", "gate_open",
        "supply_series", "price_series", "nft_last_sales", "dev_activity",
        # v4 migration + IMD launchpad (Task 1, 2026-08-23): strings, a
        # tri-state bool and a list -- same reasoning as the block above,
        # applied to the new contract surface.
        "pool_venue", "pool_id_source", "lp_state", "launchpad_as_of_hhmm",
        "burn_ready", "launchpad_coins",
        "sig_decoy_state", "sig_decoy_detail",
        "sig_burnready_state", "sig_burnready_detail",
        "sig_hot_state", "sig_hot_detail",
        # surf-launchpad-panels plan, Task 1: two more list[dict] payloads,
        # same reasoning as launchpad_coins/dev_activity above -- a list has
        # no numeric zero to confuse with a failed read.
        "launchpad_activity", "launchpad_burnkeepers",
        # -- the p POOL4 body (2026-09-01) -------------------------------
        #
        # Thirteen of the forty-five pool4 keys, and every one of them for
        # the reason this bucket exists rather than because it was easier
        # than finding a needle: the other thirty-two ALL have real,
        # screen-verified probes below, which is the first time this file's
        # numeric bucket has taken a whole contract block with no exclusions
        # at all.
        #
        # Four closed-vocabulary or free-text strings, four addresses:
        "pool4_network", "pool4_as_of_hhmm",
        "pool4_discovery_state", "pool4_discovery_detail",
        # S18: the citation, split back out of the detail. A transaction hash
        # is a string with no numeric zero to confuse with a failed read, so
        # it belongs here for this bucket's ordinary reason -- and `None` on
        # it means "no adoption to cite", which is the honest state on the
        # day-one undiscovered path rather than a missing read.
        "pool4_discovery_source_tx",
        "pool4_hook_addr", "pool4_token_addr",
        "pool4_vault_addr", "pool4_dripper_addr",
        # Two tri-state bools. `False` is a real answer on both and renders
        # as its own word -- `not yet` / `drifted` -- sharing no substring
        # with either the confident yes or the unknown, which is the rule
        # `SurfBurnPipeline._ready_word` set and both panels follow.
        "pool4_backstop_centred", "pool4_can_drip",
        # Three list payloads. `[]` and `None` are different facts on
        # `pool4_flow` (swept-and-quiet vs the read failed) and the screen
        # renders them as different sentences -- pinned by
        # `tests/screens/test_surf_screen.py::
        # test_a_quiet_pool4_sweep_is_not_a_dead_one` rather than here,
        # because it is a claim about two renders and this file's sweep only
        # looks at one.
        "pool4_reserve_series", "pool4_flow", "pool4_hatches",
        # The counter reconciliation (W1, 2026-09-02): a closed state word
        # and a free-text detail, neither with a numeric zero to confuse with
        # a failed read. They belong here for the same reason every other
        # `*_state`/`*_detail` pair in this set does.
        #
        # Worth reading twice, because it is the one place this bucket's
        # usual reasoning is not the whole story: `None` on
        # `pool4_counter_state` means the check has **never run**, and
        # `"unchecked"` is a separate member the producer can actually
        # assert. So the two are different claims and must not collapse into
        # each other -- which is the same shape as the zero-vs-`None` rule
        # this file exists for, in a vocabulary rather than in a number. It
        # is not observable *here* (this sweep renders one all-`None` frame,
        # where both would have to read as "no answer" anyway); the widget's
        # own tests are where the distinction is rendered and pinned.
        "pool4_counter_state", "pool4_counter_detail",
        # The mainnet topology (2026-09-02): two closed vocabulary words, an
        # address, and the provenance word. Strings, so no numeric zero to
        # confuse with a failed read.
        #
        # `pool4_reward_path` and `pool4_discovery_source` are the two that
        # matter for this bucket's *reason* rather than its rule: both are
        # DISCLOSURES. "three-way" says a Distributor is in the path and the
        # staker leg is split again; "docs" says the adoption came from a page
        # anyone who can edit it could have written, rather than from a
        # dev-signed post. A `None` on either is "we do not know", which must
        # never render as the safer of the two answers.
        "pool4_reward_path", "pool4_distributor_addr", "pool4_discovery_source",
    }
)

#: Numeric keys with *no render path this acceptance test can observe*, each
#: with the specific reason a zero there could never mislead a user (see
#: task-WP6.8-report.md for the full writeup and how each was verified).
_NUMERIC_KEYS_EXCLUDED: dict[str, str] = {
    # Computed by the manager (surf_manager._market_payload) but never read
    # by screens/surf.py or any widgets/surf/* module -- grep confirms no
    # `data.get("eth_usd")` call exists anywhere in either package. A
    # fabricated 0 here cannot mislead anyone because it never reaches a
    # pixel; if a future screen edit starts reading it, this key must move
    # into `_NUMERIC_ZERO_PROBES` in the same change.
    "eth_usd": "never read by screens/surf.py or any widgets/surf/* module",
    # Mentioned only in a code comment in screens/surf.py; never passed to
    # StatusBar.update_data or any widget's update_data.
    "as_of": "never read by screens/surf.py or any widgets/surf/* module",
    # Was probed as `"· L 0"` until the hero's liquidity field was dropped on
    # request (a raw v3 uint128 renders `2.16e+18`, which names no unit and
    # says nothing `142.71 WETH` does not). The key is still computed and the
    # LP MIGRATION detector still reads it -- it simply has no box any more,
    # so a fabricated 0 cannot reach a pixel through the hero. Moved here
    # deliberately rather than left in place: the old probe would have gone
    # on passing, because a substring that can never render is trivially
    # absent, and this suite has already produced five tests that passed for
    # exactly that kind of reason. If a future widget renders it, move this
    # key back into `_NUMERIC_ZERO_PROBES` in the same change.
    "lp_liquidity": "dropped from the hero LP box; no widget renders it",
    # -- the mainnet block, 2026-09-02 -------------------------------------
    #
    # The three `*_bps` keys render as a share OF A DENOMINATOR. Under the
    # full outage this test sweeps, `pool4_bps_denominator` is `None`, so the
    # panel prints `stakers --` however the numerator reads and a fabricated
    # 0 cannot reach a pixel as a number. Structurally unobservable here, the
    # same shape as the `sig_*_age_s` entries above -- verified by rendering
    # each one zeroed, not assumed.
    "pool4_distributor_staking_bps":
        "renders as a share of pool4_bps_denominator, which is None under outage",
    "pool4_distributor_nodes_bps":
        "renders as a share of pool4_bps_denominator, which is None under outage",
    "pool4_distributor_bonding_bps":
        "renders as a share of pool4_bps_denominator, which is None under outage",
    # ⚠ NOT a design decision -- A DEFECT IN ANOTHER PACKAGE, parked here with
    # its evidence rather than hidden.
    #
    # `screens/surf.py` dispatches `pool4_cap_headroom` to `SurfPool4Ratchet`
    # exactly as WP0's `POOL4_WIDGET_SIGNATURES` requires, but that widget's
    # `update_data` does not declare the parameter, so `**_kwargs` swallows
    # it and the value reaches no pixel at any width. Verified twice: the
    # string `headroom` appears nowhere in `widgets/surf/pool4_ratchet.py`,
    # and zeroing the key through the real screen produces no new line at
    # all where every other numeric key produces one.
    #
    # It is the inventory ceiling's headroom -- the number that says how
    # close the cap is to binding (94.68 IMD, ~2.3 hours, on mainnet) -- so
    # this is a missing reading rather than a cosmetic gap. Filed against
    # WP4; not worked around here, because a screen-side workaround would
    # make the widget look correct.
    "pool4_cap_headroom":
        "DEFECT: SurfPool4Ratchet.update_data does not accept it; **_kwargs "
        "swallows the dispatch and it renders nowhere. Filed against WP4.",
    # widgets/surf/signals.py `_head()` reads `age_s` only inside the
    # `state == "fired"` branch; every other state -- including the `None`
    # a full outage produces -- ignores it entirely, so `{state: None,
    # age_s: 0}` renders byte-identical output to `{state: None, age_s:
    # None}`. The None-vs-0 rule for these six fields can only be observed
    # under a FIRED state, and this acceptance test's whole premise is that
    # no signal may fire under a full outage (see the `"FIRED" not in text`
    # assertion below) -- so it structurally cannot exercise them.
    "sig_post_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_lp_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_gate_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_deploy_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_bridge_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_burn_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_thread_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    # v4 migration + IMD launchpad (Task 1, 2026-08-23). Every key below
    # HAS a representable zero at the model/manager layer -- "0" means "we
    # looked and nothing has accrued/happened", distinguishable from a
    # failed-read `None` -- so none of these belong in `_NON_NUMERIC_KEYS`.
    # They are excluded from `_NUMERIC_ZERO_PROBES` for a narrower reason:
    # no widget dispatches any of them yet (Tasks 8-12 wire the screen;
    # see `tests/screens/test_surf_screen.py::_KEYS_PENDING_CONSUMERS`), so
    # there is no real render to verify a zero-substring against today --
    # putting an unverified guess in `_NUMERIC_ZERO_PROBES` would pass this
    # test for the wrong reason, exactly the anti-pattern the `lp_liquidity`
    # entry above was already moved here to avoid. Each one must move to
    # `_NUMERIC_ZERO_PROBES` with a real, screen-verified substring in the
    # same change that wires its consumer -- same rule as `eth_usd` and
    # `lp_liquidity` above, just newly arrived.
    #
    # `pool_fee_bps`, `decoy_pool_count`, `burn_accrued` and `burn_staged`
    # moved out of this dict in Task 8 (SurfHero's `_pool_lines`/
    # `_burn_lines` now render all four) -- see `_NUMERIC_ZERO_PROBES` below.
    # `screens/surf.py` itself is not rewired yet (Task 12), so the
    # needles were verified by mounting `SurfHero` directly (one field
    # zeroed at a time, all others `None`, against the true all-`None`
    # baseline), not against the real running `SurfScreen` -- the same
    # method the pre-existing entries below document, just against the box
    # rather than the screen because the screen cannot reach these keys
    # yet. They become genuinely screen-verified the moment Task 12 wires
    # `update_data(pool_fee_bps=..., decoy_pool_count=..., burn_accrued=...,
    # burn_staged=...)` through.
    #
    # `burn_min_bridge`, `launchpad_coin_count`, `launchpad_swap_count`,
    # `launchpad_trader_count`, `launchpad_burned_total` and
    # `launchpad_creator_eth_owed` moved out the same way in Task 11
    # (`widgets/surf/launchpad.py`'s three new widgets now render all six)
    # -- see `_NUMERIC_ZERO_PROBES` below. Same method again: mounted
    # `SurfLaunchpadCoins`/`SurfCurveFlow`/`SurfBurnPipeline` directly (one
    # field zeroed, every other field `None`, checked against the true
    # all-`None` baseline of the *same widget*), because `screens/surf.py`
    # still cannot reach these keys until Task 12 wires the `l` view.
    # Fix round 10a (2026-08-24): the v4-pool-id-matched market fix.
    # `legacy_pool_liquidity_usd` USED to sit here too ("no widget consumer
    # yet") -- stale since Task 10 wired `market.py`'s `legacy_line`
    # (`_parts`); it moved to `_NUMERIC_ZERO_PROBES` below once Task 13
    # verified its needle by rendering the real screen.
    #
    # `price_source_disagreement_pct` is also dispatched to
    # `SurfMarket.update_data()` now (Task 10), but stays here -- not
    # because nothing consumes it, but because its one render path
    # genuinely cannot distinguish a genuine 0 from a failed read.
    # `_price_marker` (widgets/surf/market.py): `if v is None or abs(v) <=
    # _PRICE_DISAGREEMENT_PCT: return ""` -- a real 0.0 (perfect agreement)
    # and a failed `None` read take the *same* branch to the *same* empty
    # string, by design (the docstring: "[None] is also not a disagreement
    # to flag: it renders no marker at all, same as a value inside the
    # threshold"). Verified by rendering `SurfMarket` side by side (Task
    # 13): `price_source_disagreement_pct=0.0` and `=None` composite a
    # byte-identical price row (`IMD $0.7074`, no marker), while `=5.0`
    # (past the 2.0-point threshold) composites `IMD $0.7074 ?` -- proving
    # the code path is real and that 0 specifically does not reach it.
    # There is no substring a genuine 0 produces that `None` does not, so
    # unlike its sibling above this key has no zero-catch needle to probe.
    "price_source_disagreement_pct": (
        "dispatched to SurfMarket.update_data(); _price_marker renders a "
        "genuine 0 and a failed None read identically (both take the "
        "'no marker' branch), verified by rendering -- no needle exists"
    ),
    # Same age_s-only-on-FIRED reasoning as the six existing sig_*_age_s
    # entries just above -- these three new detectors follow the identical
    # widgets/surf/signals.py `_head()` pattern once Task 9 wires them.
    # Final fix wave (I3): two probes moved BACK here, because rendering them
    # proved they were asserting the absence of strings the outage scenario
    # cannot produce. A vacuous probe is worse than an honest exclusion --
    # it reads as coverage while testing nothing, which is the rule the
    # `lp_liquidity` entry at the top of this dict already states.
    #
    # `identities_written` has NO widget consumer at all. The hero box that
    # used to render it (`_update_gate`) was replaced by POOL/LP/BURN/SUPPLY
    # in Task 8, and `screens/surf.py` does not dispatch the key anywhere
    # (its own comment says so); IDENTITY.MD's `N/2000 written` cell reads
    # `nft_written`, which has its own probe below. The information still
    # reaches the screen -- through `sig_gate_detail`, a *string* the manager
    # composes inside `build_signals` from the LOG-window count, not from
    # this key -- so a payload-level zero here renders nothing to probe.
    # Verified by rendering: `identities_written=0` with every other key
    # `None` composites no `0/2000` anywhere on the screen.
    "identities_written": (
        "no widget consumes this key -- the hero GATE box it was measured "
        "against was replaced in Task 8 and screens/surf.py dispatches it "
        "nowhere; verified by rendering"
    ),
    # `launchpad_coin_count` IS rendered (`SurfLaunchpadCoins._set_note`), but
    # never under a full outage: `_set_note` checks `coins is None` FIRST and
    # renders `⚠ launchpad unavailable` instead of any count, which is the
    # correct behaviour. Giving this test a payload where `coins` is a list
    # would not fix it -- that payload is not an outage, and a genuine 0
    # SHOULD then render `0 coins`. Verified by rendering both ways.
    "launchpad_coin_count": (
        "SurfLaunchpadCoins._set_note pre-empts the count with 'launchpad "
        "unavailable' whenever `coins` is None, which a full outage always "
        "is -- so a zero has no rendering here to probe; verified by rendering"
    ),
    # Task 12 (2026-08-24) wired `screens/surf.py` to pass this through as
    # `SurfLaunchpadCoins.update_data(launch_count=...)` -- the kwarg the
    # widget had accepted since Task 11 and nothing ever sent, which is why
    # the population-disagreement note could not fire in the running app at
    # all. It lands HERE and not in `_NUMERIC_ZERO_PROBES` for exactly its
    # sibling `launchpad_coin_count`'s reason, one entry up: `_set_note`
    # renders it only inside `<count> coins · <read> read`, and only when
    # `coins` is a list AND `coin_count` disagrees with it. Verified by
    # rendering the real screen three ways at (143, 48): with
    # `launch_count=0, coin_count=146, coins=[]` the note composites
    # `146 coins · 0 read`; with `launch_count` left `None` and the same
    # shape it composites `146 coins` and nothing more (so the needle really
    # is the zero's, not the shape's); and with `coins=None` -- which every
    # full outage is -- it composites `⚠ launchpad unavailable` whatever
    # `launch_count` holds. A needle for a string the swept scenario cannot
    # produce is the vacuity this dict exists to keep out.
    "launchpad_launch_count": (
        "SurfLaunchpadCoins._set_note renders it only as the `· N read` half "
        "of a population disagreement, which needs `coins` to be a list -- a "
        "full outage always has it None and composites 'launchpad "
        "unavailable' instead; verified by rendering three ways"
    ),
    # Both orphaned by the hero's 2026-08-24 LAUNCHPAD/FLOW rebuild, which
    # retired the POOL box `hero.py::_pool_lines` drew. They were in
    # `_NUMERIC_ZERO_PROBES` with needles naming that function, and were
    # vacuous from the day it was deleted -- the suite stayed green because
    # these assertions test *absence*, which is the trap this dict's own
    # `lp_liquidity` entry at the top already names. `screens/surf.py` no
    # longer dispatches either key to any widget (see
    # `tests/screens/test_surf_screen.py::_KEYS_WITHOUT_A_RENDERER` and
    # `META_KEYS`). Verified by rendering the real SurfScreen at (143, 48)
    # with each key `0` and every other `None`: no `% fee`, no `pools`, and
    # no `WETH` reaches a pixel anywhere on either body.
    #
    # `decoy_pool_count` is not information-less on screen -- `_readings`
    # feeds it to `_detect_decoy`, so it reaches the rail as the DECOY POOL
    # row's *detail string* -- but that is `sig_decoy_detail`'s rendering,
    # composed by the manager, exactly the `identities_written` case above.
    "pool_fee_bps": (
        "no widget consumes this key -- the hero POOL box that rendered it "
        "(`_pool_lines`) was retired in the 2026-08-24 rebuild and "
        "screens/surf.py dispatches it nowhere; verified by rendering"
    ),
    "decoy_pool_count": (
        "no widget consumes this key directly -- the hero POOL box that "
        "rendered it was retired; it reaches the screen only through "
        "`sig_decoy_detail`, a string the manager composes, the same shape "
        "as `identities_written` above; verified by rendering"
    ),
    "lp_imd": (
        "no widget consumes this key -- the hero LP box that rendered it "
        "(`_update_lp`) was retired in the 2026-08-24 rebuild and "
        "screens/surf.py dispatches it nowhere; verified by rendering"
    ),
    "lp_weth": (
        "no widget consumes this key -- the hero LP box that rendered it "
        "(`_update_lp`) was retired in the 2026-08-24 rebuild and "
        "screens/surf.py dispatches it nowhere; verified by rendering"
    ),
    "sig_decoy_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_burnready_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
    "sig_hot_age_s": "state is None under outage; _head() reads age_s only when state == 'fired'",
}

#: Numeric keys this test DOES probe: key -> the exact substring the real
#: widget/screen formatter renders for a *genuine* ``0`` in that field, each
#: with enough surrounding context that it cannot be confused with a bare
#: ``"0"`` that legitimately appears elsewhere on screen (an address, a block
#: number, the version tail, the poll interval). Verified empirically against
#: the real ``SurfScreen`` at the pinned ``(143, 48)`` size -- one field
#: zeroed at a time, all others ``None`` -- and against the true all-``None``
#: baseline to rule out false-positive collisions. Some substrings are
#: shortened to survive box truncation at this width (e.g. ``identities_written``
#: renders ``"0/2000 writt…"`` inside the narrow GATE hero box).
_NUMERIC_ZERO_PROBES: dict[str, str] = {
    # RE-POINTED at the ANNOUNCE panel's own title (final fix wave, N1).
    # Both needles used to read the title bar's `feed #N (age)` segment, which
    # was the ONLY render path either key had -- and I4 traded that segment
    # away one commit after I3 fixed exactly this class of defect, so both
    # probes went vacuous in the same wave that was auditing them. The suite
    # stayed green because these assertions test *absence*, which is the trap.
    # `widgets/surf/feed.py::_set_title` composes `ANNOUNCE FEED · #N · last
    # <age> ago`, so a genuine zero in either key still reaches a pixel there.
    # Re-verified by rendering the real SurfScreen at (143, 48) with one key
    # 0 and every other None: both appear, and neither is in the all-`None`
    # baseline, which composites `ANNOUNCE FEED · unavailable`.
    "feed_nonce": "· #0 ·",                      # feed.py _set_title
    "feed_last_post_age_s": "last 0s ago",       # feed.py _set_title
    # `lp_imd` ("0 IMD") and `lp_weth` ("0.00 WETH") sat here until Task 12
    # (2026-08-24) and were vacuous from the moment the hero's LP box was
    # retired -- `hero.py::_update_lp`, the function both needles name, no
    # longer exists. They moved to `_NUMERIC_KEYS_EXCLUDED` above, verified
    # by rendering. Note that `lp_imd`'s needle was also a *duplicate* of
    # `imd_supply`'s, one line below: it could only ever have gone red on
    # the sibling's rendering, never its own.
    "imd_supply": "0 IMD",                       # hero.py _supply_lines
    # The field's own honest zero rendering (distinct from `imd_burned_cum
    # is None` -> "burned --"): this is the exact shape the house rule
    # guards -- a fabricated 0 here would falsely claim "we watched and
    # nothing moved" instead of the honest "we could not read this".
    "imd_burned_cum": "no burn obser",           # hero.py _update_supply
    "imd_price_usd": "$0.00",                    # market.py fmt_price (pre-existing check)
    # The gap is TWO spaces and it is not a typo: `_labelled` pads every row
    # label to the width of the widest (`IMD`), so `FP` renders one column
    # short and then its own separator. Verified by rendering the real
    # SurfScreen at (143, 48) with only this key set to 0.0 -- the old
    # single-space `FP $0.00` composited nowhere and probed nothing.
    "fp_price_usd": "FP  $0.00",                 # market.py fmt_price
    # Same shape one row down: `_window` pads `24h ±` to the width of
    # `parity`. Verified by rendering with this key 0.0 AND `imd_price_usd`
    # set -- the change cell renders beside the price row, and the old
    # `+0.00% 24h` had the two halves in the wrong order entirely.
    "imd_change_24h_pct": "24h ±  ● +0.00%",     # market.py _fmt_change
    "imd_vol_24h_usd": "vol 24h $0",             # market.py fmt_compact
    "pool_liquidity_usd": "pool $0",             # market.py fmt_compact
    # Correct as it stood, but it needed re-verifying the hard way: `_parts`
    # gates the parity cell on all THREE market keys, so a payload with only
    # `parity_pct` set renders `parity --` and proves nothing. Rendered with
    # `imd_price_usd` and `fp_price_usd` set alongside it.
    "parity_pct": "parity ● +0.00%",        # market.py _fmt_parity
    # Task 8 (2026-08-23): SurfHero's BURN box. `pool_fee_bps` ("0% fee") and
    # `decoy_pool_count` ("1 of 1 pools") were beside these two until Task 12
    # (2026-08-24) and were vacuous the moment the POOL box was retired --
    # `hero.py::_pool_lines`, the function both needles name, no longer
    # exists, and the screen no longer dispatches either key. Both moved to
    # `_NUMERIC_KEYS_EXCLUDED` above, verified by rendering. The two below
    # survive unchanged: `_burn_lines` is still on the row, and Task 12's
    # dispatch rewire kept `burn_accrued`/`burn_staged` pointed at it, so
    # these are now screen-verified rather than box-verified. Re-read off the
    # real `SurfScreen` at (143, 48) with one key `0` and every other `None`:
    # `acc 0 · stg --` and `acc -- · stg 0`.
    "burn_accrued": "acc 0",                     # hero.py _burn_lines
    "burn_staged": "stg 0",                      # hero.py _burn_lines
    # Task 12 (2026-08-24): the hero's LAUNCHPAD box, wired through the real
    # screen at last. Both needles were READ off composited output at the
    # pinned (143, 48) -- one key `0`, every other key `None` -- not invented:
    # the box's second line renders `0 new · 24h` and its third `0 creators`,
    # while the all-`None` baseline collapses both into a single `no read yet`
    # (the three-state contract `_launchpad_lines` documents), so neither
    # needle exists in the outage render. `· 24h` is part of the first needle
    # deliberately: the box drops that suffix at its narrow tiers, so the long
    # form is what pins the width this test actually renders at.
    "launchpad_new_24h": "0 new · 24h",          # hero.py _launchpad_lines
    "launchpad_creator_count": "0 creators",     # hero.py _launchpad_lines
    "nft_holders": "0 holders",                  # nft.py _fmt_count
    "nft_transfers_24h": "0 transfers/24h",      # nft.py _fmt_count
    "nft_dev_holdings": "dev holds 0 identities",  # nft.py _dev_row
    # Was `identities 0/2000 written` while the written count had a row of its
    # own. It moved onto the stats row and lost the leading `identities` word
    # (which now labels the dev holdings), so the old probe went absent for the
    # wrong reason -- a needle this test only ever asserts is *missing* stops
    # covering anything the moment the render stops being able to produce it.
    "nft_written": "0/2000 written",             # nft.py _stats_variants
    # The honesty flagship the widget's own module docstring names: "never
    # faked, never 0, never silently blank". A genuine 0 renders with units;
    # a failed read must render `FLOOR_UNAVAILABLE`, never this string.
    "nft_floor": "0.000 ETH",                    # nft.py update_data
    # Task 11 (2026-08-23): the launchpad widgets. `screens/surf.py` doesn't
    # route these keys through yet either (Task 12), so -- same method as
    # the Task 8 four just above -- these were verified by mounting
    # `SurfLaunchpadCoins`/`SurfCurveFlow`/`SurfBurnPipeline` directly, one
    # field zeroed at a time with every other field on that widget `None`,
    # against the true all-`None` baseline of the same widget.
    "launchpad_swap_count": "0 swaps",           # launchpad.py _flow_lines
    "launchpad_trader_count": "0 traders",       # launchpad.py _flow_lines
    "launchpad_creator_eth_owed": "owed 0.0000 ETH",  # launchpad.py _flow_lines / _fmt_eth_owed
    # `fmt_imd` since 2026-08-25, not `fmt_compact`: the house helper renders
    # everything below 1.0 with zero decimals, which is most of this pipeline
    # for the minutes after each sweep.
    "burn_min_bridge": "min bridge 0.00 IMD",    # launchpad.py _pipeline_lines
    # `previewBridge().amountToSend` -- what a burn would send right now. A
    # real on-chain zero here is "nothing is bridgeable", which is exactly
    # what the status word beside it then says.
    "burn_bridgeable": "0.00 IMD",               # launchpad.py _pipeline_lines
    "launchpad_burned_total": "burned 0 IMD (all-time)",  # launchpad.py _pipeline_lines / _fmt_total
    # Fix round 10a / Task 13 (2026-08-23): `screens/surf.py` now routes
    # this through `SurfMarket.update_data()` (`market.py`'s `legacy_line`
    # in `_parts`, gated on `legacy is not None` -- a genuine 0.0 passes
    # that gate, `None` does not). Verified by rendering the real
    # `SurfScreen` at the pinned (143, 48) size with only this key set to
    # `0.0`: the market panel composites `legacy: v3 pool $0`, absent with
    # the key `None`. Its sibling `price_source_disagreement_pct` stays in
    # `_NUMERIC_KEYS_EXCLUDED` above precisely because the same
    # side-by-side check found no such needle for it.
}

#: The ``p`` POOL4 body's thirty-two numeric keys, every needle read off
#: composited output rather than guessed.
#:
#: Method, and it is the one this file's own history insists on: render the
#: **real** ``SurfScreen`` at (143, 60), press ``p``, set exactly one key to
#: ``0``/``0.0`` with every other key ``None``, and diff the result against
#: the all-``None`` baseline. The needle is a substring that appears only in
#: the zeroed render. Four of ten needles went vacuous on the predecessor
#: branch by being invented before the widget existed, and two more went
#: vacuous later when the surface they named was retired -- absence-only
#: assertions cannot tell "this never rendered" from "this correctly did not
#: render".
#:
#: **So these thirty-two are not absence-only.**
#: ``test_every_pool4_zero_needle_really_renders_when_its_key_is_zero``
#: below asserts the other direction for every entry, one key at a time: the
#: needle MUST appear when its key is zero. A needle that goes stale --
#: because a label's padding changed, or a panel was re-worded -- fails there
#: instead of quietly passing here forever. That positive control is the
#: thing this file has been missing, and adding it for a whole block at once
#: is cheaper than retrofitting it later.
#:
#: **No pool4 key is in ``_NUMERIC_KEYS_EXCLUDED``.** Every one of the
#: thirty-two reaches a pixel in the ``p`` body, so none of them needs the
#: "no observable render path" waiver -- and the waiver is the entry that
#: rots, because it is a judgement ("and that is fine") wearing a fact's
#: clothes.
_POOL4_ZERO_PROBES: dict[str, str] = {
    # THE SPLIT
    #
    # FOUR OF THESE WENT STALE ON 2026-09-02 and the positive control below
    # is what said so. WP5 reworked this panel for the mainnet three-way
    # split -- `burn`/`stakers` gained their `measured ` prefix and the
    # claimed share became `claimed reward N/D bps` -- so four needles that
    # had been asserting an ABSENCE went on passing while the strings they
    # named could no longer render at all. That is precisely the vacuous
    # half this file's history is full of, caught this time by the test that
    # renders each needle rather than by somebody noticing.
    "pool4_measured_inference_pct": "measured inference 0.00%",
    "pool4_measured_burn_pct": "measured burn 0.00%",
    "pool4_measured_stakers_pct": "measured stakers 0.00%",
    "pool4_reward_share_bps": "claimed reward 0/-- bps",
    "pool4_bps_denominator": "claimed reward --/0 bps",
    # 0.0 is the HEALTHY value of the drift and renders as a number by
    # design (the contract says so twice). The needle is still correct: the
    # forbidden thing is a *failed read* rendering as that number, and under
    # a full outage the key is None, so the sentence must be absent.
    "pool4_split_drift_bps": "drift 0.00 bps",
    "pool4_total_burned": "burned 0 IMD ·",
    "pool4_total_rewarded": "rewarded 0 IMD",
    "pool4_total_fee_token": "fees 0 IMD",
    "pool4_retained_eth": "retained 0.0000 ETH",
    "pool4_last_claim_block": "last claim block 0",
    "pool4_unsettled_burn": "unsettled burn 0.00 IMD",
    "pool4_unsettled_stakers": "unsettled stakers 0.00 IMD",
    # THE RATCHET
    "pool4_tokens_in_pool": "reserve  0 IMD",
    "pool4_cap_floor": "floor    0 IMD",
    "pool4_floor_distance": "vs floor 0 IMD",
    "pool4_floor_distance_pct": "· +0.0%",
    "pool4_burned_supply_pct": "burned   0.00%",
    "pool4_total_supply": "of 0 IMD",
    "pool4_eth_in_pool": "pool     0.000000 ETH",
    "pool4_position_liquidity": "· L 0",
    "pool4_current_tick": "tick     0 ·",
    "pool4_ref_tick": "· ref 0",
    # sIMD VAULT
    "pool4_share_price": "share 0.000000 IMD/sIMD",
    "pool4_share_price_delta_pct": "· +0.00%",
    "pool4_vault_assets": "TVL   0 IMD",
    "pool4_vault_shares": "· 0 sIMD",
    "pool4_drip_per_day": "drip  0 IMD/day",
    "pool4_drippable": "· 0 IMD drippable",
    "pool4_backlog_imd": "queue 0 IMD",
    "pool4_backlog_days": "· 0.0 days of runway",
    # ``deliv``, not ``apr``: WP4 retired the APR label because the protocol
    # publishes a differently computed APR under that word, and moved the
    # disclaimer onto the number's own line
    # (``deliv 0.00% · drip rate ÷ TVL, not APR``). Only the figure is the
    # needle -- taking the disclaimer with it would couple this probe to the
    # wording of a note rather than to the zero it exists to prove.
    "pool4_implied_apr_pct": "deliv 0.00%",
    # -- the mainnet distributor and the inventory ceiling (2026-09-02) ----
    #
    # Seven of the eleven new numeric keys. Every needle below was READ OFF
    # composited output through the real ``SurfScreen`` with that one key
    # zeroed and every other key ``None`` -- never guessed. The first draft
    # of this block WAS guessed and four of its eleven needles were wrong,
    # which the positive control caught immediately; the other four keys are
    # in ``_NUMERIC_KEYS_EXCLUDED`` below because rendering showed they have
    # no observable zero at all.
    #
    # The needles carry their neighbours' dashes on purpose. ``earned 0.00``
    # alone would match whichever of the three legs was zeroed, so the leg's
    # own label is part of the needle and a swap between two legs is visible
    # rather than absorbed.
    #
    # ⚠ ALL FIVE WERE RE-READ ON 2026-09-02. They were never wrong about the
    # rendering -- the rendering changed under them: WP5's D19 gave each leg
    # head a liveness word (``live`` / ``reserve`` / ``derived, reserve``),
    # so ``stakers --`` became ``stakers -- live``. The needles went on
    # asserting an ABSENCE that no longer had anything to be absent, which is
    # the vacuous half again, and five of the six were reachable only after
    # the sixth was fixed -- see the parametrised probe below, which is why
    # they are visible as five failures rather than as one.
    "pool4_distributor_staking_earned": "stakers -- live · earned 0.00",
    "pool4_distributor_nodes_earned": "nodes -- reserve · earned 0.00  held --",
    "pool4_distributor_bonding_earned":
        "bonding -- derived, reserve · earned 0.00  held --",
    "pool4_distributor_held_nodes": "nodes -- reserve · earned --  held 0.00",
    "pool4_distributor_held_bonding":
        "bonding -- derived, reserve · earned --  held 0.00",
    "pool4_inventory_cap": "cap      0 IMD",
    # A rate of zero renders as the WORDS, not as a number -- and that is the
    # zero rendering for this key, so it is what a failed read must not
    # produce. ``None`` renders neither.
    "pool4_cap_decay_per_day": "no decay",
}

#: **Emptied by Task 12** (2026-08-24), which wired the last three consumers.
#: It held keys whose rendering consumer landed in a later task of this plan:
#: numeric keys that WILL need real zero-catch probes, kept out of
#: `_NUMERIC_ZERO_PROBES` in the meantime because a probe string invented
#: before the widget exists passes by absence and proves nothing -- which is
#: how four of ten needles went vacuous on the predecessor branch.
#:
#: Where the three went, each read off composited output rather than guessed:
#: `launchpad_new_24h` and `launchpad_creator_count` to `_NUMERIC_ZERO_PROBES`
#: (the hero's LAUNCHPAD box renders both), and `launchpad_launch_count` to
#: `_NUMERIC_KEYS_EXCLUDED` -- its one render path is pre-empted under the
#: outage this test sweeps, exactly like its sibling `launchpad_coin_count`.
#: The brief expected all three in the probes dict; rendering them is what
#: said otherwise, and a vacuous probe is worse than an honest exclusion.
#:
#: Kept as an empty frozenset rather than deleted: it is the bucket the next
#: freeze-before-the-consumer-exists key goes into, and
#: `test_every_surf_key_is_triaged_for_the_zero_catch` still partitions
#: against it.
_KEYS_PENDING_CONSUMERS = frozenset()


def test_every_surf_key_is_triaged_for_the_zero_catch() -> None:
    """A SURF_KEYS key added later must be triaged, not silently uncovered.

    Four disjoint buckets -- checked, numeric-but-unobservable, structurally
    non-numeric, and (temporarily) pending-a-consumer -- must partition
    ``SURF_KEYS`` exactly. This is what "drive it from the real key list"
    means in practice: a hand-typed list of fields to check would silently
    stop covering the contract the moment ``SURF_KEYS`` grows, which is
    exactly the shape of the finding this test exists to close.

    ``_KEYS_PENDING_CONSUMERS`` is scaffolding, not a permanent fourth
    bucket -- see ``test_the_pending_consumer_bucket_is_empty_by_the_end_of_this_plan``,
    which is what stops it from becoming one.
    """
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    checked = set(_NUMERIC_ZERO_PROBES) | set(_POOL4_ZERO_PROBES)
    excluded = set(_NUMERIC_KEYS_EXCLUDED)
    non_numeric = set(_NON_NUMERIC_KEYS)
    pending = set(_KEYS_PENDING_CONSUMERS)

    overlap = (
        (checked & excluded)
        | (checked & non_numeric)
        | (checked & pending)
        | (excluded & non_numeric)
        | (excluded & pending)
        | (non_numeric & pending)
    )
    assert not overlap, f"a key is triaged into more than one bucket: {overlap}"

    covered = checked | excluded | non_numeric | pending
    missing = set(SURF_KEYS) - covered
    assert not missing, (
        f"SURF_KEYS grew a key this test never triaged: {missing} -- add it "
        "to _NUMERIC_ZERO_PROBES, _NUMERIC_KEYS_EXCLUDED, _NON_NUMERIC_KEYS "
        "or _KEYS_PENDING_CONSUMERS"
    )
    extra = covered - set(SURF_KEYS)
    assert not extra, f"triaged a key SURF_KEYS no longer has: {extra}"


def test_no_surf_key_is_still_waiting_for_a_consumer():
    """`_KEYS_PENDING_CONSUMERS` is scaffolding with an expiry date.

    Task 12 wired the last consumer and re-triaged every entry with a needle
    (or an exclusion) verified against composited output. This test is what
    stops the scaffolding from becoming permanent, and it lost its `xfail`
    marker in the same change that emptied the set -- a self-deleting marker
    left behind outlives the thing it was waiting for and turns a real
    regression back into an expected failure.

    It used to read ``assert _KEYS_PENDING_CONSUMERS == frozenset()``, which
    compares a constant defined a few dozen lines above against the literal
    it was assigned and can therefore only fail if somebody edits that line
    on purpose. Adding an unconsumed key to ``SURF_KEYS`` and parking it in
    the pending bucket -- the exact regression the scaffolding could decay
    into -- left it green.

    The honest form of the same claim is against the **contract**: every
    ``SURF_KEYS`` key must land in one of the three buckets that carry a
    rendering claim (a zero-probe needle, a documented reason it cannot be
    observed, or "not a number"). The pending bucket carries no such claim,
    so a key in it is a key nothing has looked at.
    """
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    triaged = (
        set(_NUMERIC_ZERO_PROBES)
        | set(_POOL4_ZERO_PROBES)
        | set(_NUMERIC_KEYS_EXCLUDED)
        | set(_NON_NUMERIC_KEYS)
    )
    waiting = set(SURF_KEYS) - triaged
    assert not waiting, (
        f"{sorted(waiting)} reach no consumer yet -- give each one a probe "
        "needle, an exclusion with a reason, or a place in "
        "_NON_NUMERIC_KEYS, rather than leaving it in "
        "_KEYS_PENDING_CONSUMERS"
    )
    # ...and the bucket really is the empty scaffolding the paragraph above
    # says it is, which is now a *consequence* of the line above rather than
    # the whole test.
    assert not set(_KEYS_PENDING_CONSUMERS) - waiting


def test_a_full_outage_renders_explicit_states_not_zeros() -> None:
    """Every detector is on screen, none of them reads as a live number.

    ``0`` is the forbidden rendering: CLAUDE.md's "a failed read is None,
    never 0" exists because a zeroed supply reads as a 100% burn. Checked
    across the numeric surface of ``SURF_KEYS`` (see ``_NUMERIC_ZERO_PROBES``
    above), not just the price.

    ``DeadSourcesManager`` sets every ``SURF_KEYS`` entry to ``None``, so all
    nine detectors are unknown -- and unlike ``ok``, unknown rows never fold
    (``widgets/surf/signals.py``'s Quiet-collapse section). All nine must
    therefore still keep their own line under a full outage; none may
    disappear into a quiet summary that would misreport a dead read as calm.

    **Both bodies** (final fix wave, I3). ``l`` swaps the dashboard body for
    the launchpad's three panels, and this test used to sweep only the first
    one -- so five of the six launchpad needles asserted the absence of a
    string from a body that never composited, and the sweep silently stopped
    covering the whole ``l`` view the day it was added. The needles are swept
    against the concatenation of both renders, so a zero in either is caught.
    """
    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        app = _offline_app(DeadSourcesManager())
        async with app.run_test(size=(143, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()

            dashboard_text = _screen_text(app)
            text = dashboard_text
            for label in (
                "NEW POST",
                "LP MOVE",
                "GATE OPEN",
                "NEW DEPLOY",
                "BRIDGE STAGE",
                "BURN",
                "DECOY POOL",
                "BURN READY",
                "HOT COIN",
            ):
                assert label in text, f"{label} vanished under outage"
            assert "quiet" not in text, (
                "an unknown (dead-read) row folded into the quiet summary -- "
                "unknown rows must never fold"
            )
            # The title bar names every failing group behind the house
            # warning glyph (the prefix was the word "degraded" until
            # 2026-08-12). What this pins is end-to-end and geometric: the
            # *whole* six-name list reaches a pixel through the real app at
            # 143x48, on a row that wraps out of existence rather than
            # ellipsising -- see WORST_CASE_TITLE_COLUMNS, which measures it
            # at 139 (137 across six source groups, 142 once
            # SOURCE_LAUNCHPAD made it seven, 139 once the title bar traded
            # `feed #N (age)` for `as of HH:MM`). It does **not** pin the
            # vocabulary: the double's
            # `_degraded` is `sorted(SOURCES)` too, so a renamed group
            # renames both sides and stays green here. The rename tripwire
            # is test_degraded_sources_ride_the_house_warning_glyph_not_the_word
            # in tests/screens/test_surf_screen.py, which spells them out.
            from maxpane_dashboard.data.surf_manager import SOURCES

            assert "⚠ " + ", ".join(sorted(SOURCES)) in text, (
                "the title bar never told the operator sources are down"
            )
            assert "FIRED" not in text, (
                "a signal fired on an outage -- baselines moved on a failed read"
            )
            assert "$0.00" not in text, "a missing price rendered as zero"

            # ...and now the OTHER body. `l` (2026-08-23) swaps the five
            # dashboard panels for LAUNCHPAD COINS / CURVE FLOW / BURN
            # PIPELINE; the hero row stays mounted either way. Six of the
            # probes below only ever render in here, so sweeping one body
            # covered neither the launchpad panels nor the fact that the
            # swap happened at all.
            await pilot.press("l")
            await pilot.pause()
            launchpad_text = _screen_text(app)
            from maxpane_dashboard.widgets.surf.launchpad import (
                COINS_UNAVAILABLE,
            )

            assert COINS_UNAVAILABLE in launchpad_text, (
                "pressing `l` did not reach the launchpad body -- the sweep "
                "below would be measuring the dashboard twice"
            )

            # ...and the THIRD body (2026-09-01). `p` swaps in the POOL4
            # panels, and all thirty-two `_POOL4_ZERO_PROBES` needles only
            # ever render in here. Sweeping two bodies would have left the
            # whole pool4 block asserting the absence of strings from a body
            # that never composited -- the identical hole the `l` view left
            # open until the final fix wave's I3, repeated one body later.
            # The guard against repeating it a third time is the
            # `_body_reached` check below, which fails loudly rather than
            # letting the sweep measure the same render twice.
            await pilot.press("p")
            await pilot.pause()
            pool4_text = _screen_text(app)
            from maxpane_dashboard.widgets.surf.pool4_hatches import (
                UNAVAILABLE_LINE as HATCHES_UNAVAILABLE,
            )

            assert HATCHES_UNAVAILABLE in pool4_text, (
                "pressing `p` did not reach the pool4 body -- the sweep "
                "below would be measuring the launchpad twice"
            )
            # The pool4 body must also be explicit rather than blank: an
            # outage that renders five empty panels is exactly as wrong as
            # one that renders zeros, and neither the needle sweep below nor
            # the title-bar check above would notice.
            for title in ("HATCHES", "POOL4 FLOW", "THE SPLIT",
                          "THE RATCHET", "sIMD VAULT"):
                assert title in pool4_text, (
                    f"{title} vanished under outage"
                )
            # The network word falls back to the em dash rather than naming
            # a chain nothing has confirmed (plan section 5 R4: a testnet
            # number on an unmarked panel is fiction presented as live, and
            # a *guessed* network word on an unread one is the same defect
            # arrived at from the other side).
            assert "SEPOLIA" not in pool4_text, (
                "a panel named a network under a full outage"
            )
            assert "MAINNET" not in pool4_text

            swept = "\n".join((dashboard_text, launchpad_text, pool4_text))

            probes = {**_NUMERIC_ZERO_PROBES, **_POOL4_ZERO_PROBES}
            assert len(probes) == (
                len(_NUMERIC_ZERO_PROBES) + len(_POOL4_ZERO_PROBES)
            ), "a needle key is in both probe dicts -- one of them is dead"
            for probe_key, needle in probes.items():
                assert needle not in swept, (
                    f"{probe_key} rendered its zero-formatted string "
                    f"{needle!r} under a full outage -- a failed read must "
                    "never render as a real 0"
                )

    asyncio.run(_run())


#: The five keys the contract types ``int``; everything else is a float, and
#: the difference is visible on screen (``0`` vs ``0.00``), so a float zero
#: fed to an int key would render a needle nobody wrote.
#:
#: Hoisted out of the test body when the probe became parametrised -- a
#: per-case function cannot keep a local it needs on every case.
_POOL4_INTEGER_KEYS = frozenset({
    "pool4_reward_share_bps", "pool4_bps_denominator",
    "pool4_last_claim_block", "pool4_current_tick", "pool4_ref_tick",
})


@pytest.mark.parametrize(
    "key,needle",
    sorted(_POOL4_ZERO_PROBES.items()),
    ids=sorted(_POOL4_ZERO_PROBES),
)
def test_every_pool4_zero_needle_really_renders_when_its_key_is_zero(
    key: str, needle: str,
) -> None:
    """The positive control the absence sweep above cannot give itself.

    ``test_a_full_outage_renders_explicit_states_not_zeros`` asserts every
    needle is **absent** from an all-``None`` render. An absence assertion
    passes for two completely different reasons -- "the panel correctly
    printed a dash" and "this string could never have rendered anywhere" --
    and this file's own history is a list of needles that were quietly the
    second kind: four went vacuous on the predecessor branch by being
    invented before their widget existed, and two more went vacuous later
    when the surface they named (the title bar's ``feed #N (age)`` segment)
    was traded away one commit after a wave that was auditing exactly this.

    So each needle is rendered here on purpose: one key set to ``0``, every
    other contract key ``None``, the real ``SurfScreen`` at (143, 60) with
    ``p`` pressed. The needle must appear. A label whose padding changed, a
    formatter that gained a decimal, or a panel that was re-worded fails
    **here**, loudly, instead of turning its sibling assertion into a
    permanent no-op.

    It also pins the pairing, not just the strings: the needle for
    ``pool4_backlog_days`` must appear when *that* key is zeroed, so a needle
    copied onto the wrong key -- which is how ``lp_imd`` ended up carrying
    ``imd_supply``'s needle and could only ever have gone red on its
    sibling's rendering -- fails here too.

    **PARAMETRISED PER KEY, AND THE SHAPE IS THE POINT (A38).** This was one
    test with the assertion inside a loop, so it stopped at the first bad
    needle and reported *one* failure. There were **six**, and five of them
    were reachable only after the one before it was fixed -- so the suite
    looked one edit from green through the whole sequence, six times over.
    A probe table is a collection of independent claims and has to fail like
    one: the loop's shape was concealing exactly what this test exists to
    expose, on a file whose own docstring is a history of vacuous needles.
    Each key now fails on its own and one run names every stale needle.
    """
    import asyncio

    from tests.screens.test_surf_screen import (
        _all_none_payload, _screen_text as _surf_screen_text, _surf_app,
    )

    async def _needle_render() -> str:
        payload = _all_none_payload()
        payload[key] = 0 if key in _POOL4_INTEGER_KEYS else 0.0
        async with _surf_app(payload).run_test(size=(143, 60)) as pilot:
            await pilot.app.screen._do_refresh()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            await pilot.pause()
            return _surf_screen_text(pilot.app)

    text = asyncio.run(_needle_render())
    assert needle in text, (
        f"{key}'s zero needle {needle!r} does not render when the key IS "
        "zero -- the absence assertion in the outage sweep is therefore "
        "vacuous for this key. Re-read it off composited output rather than "
        "editing it to taste."
    )


# ---------------------------------------------------------------------------
# the documentation surfaces (CLAUDE.md, README) -- derived from GAMES
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


def test_every_visible_dashboard_is_documented() -> None:
    """A dashboard nobody documented is a dashboard nobody finds.

    Derived from ``GAMES``, so it covers dashboard eight without being
    touched -- and goes red the moment one is added to the menu and not to
    the docs.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")

    for _key, game_id, name, _desc in GAMES:
        assert f"--game {game_id}" in readme, (
            f"README's usage block never shows `maxpane --game {game_id}`"
        )
        assert name in readme, f"README never names the {game_id} dashboard"
        assert f"`{game_id}`" in claude, (
            f"CLAUDE.md's dashboard table has no `{game_id}` row"
        )


def test_claude_md_counts_the_visible_dashboards() -> None:
    """The heading states a number; ``GAMES`` is that number."""
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    word = _NUMBER_WORDS[len(GAMES)]
    assert f"## The {word} visible dashboards" in claude, (
        f"CLAUDE.md does not say 'The {word} visible dashboards' while GAMES "
        f"lists {len(GAMES)}"
    )
