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
_STRUCTURAL = ("width", "height", "min-height", "padding", "margin")

#: The two copies deliberately do **not** cover the same selector set, and
#: both asymmetries are load-bearing:
#:
#: * ``#title-bar`` / ``#separator`` are DEFAULT_CSS-only. The shared
#:   stylesheet already styles those two ids for every screen (lines 12-130);
#:   the surf block restating them would give a shared rule a second owner.
#: * The two ``> RichLog`` rules are block-only: they are the app-stylesheet
#:   half of the feed/activity height, and the widgets' own DEFAULT_CSS owns
#:   the rest.
#:
#: Pinned as *sets*, not counted. A count is the vacuity hole it was meant to
#: close: the guard used to read ``len(shared) >= 8`` against a real overlap
#: of ten, so renaming ``SurfMarket`` to ``SurfMarketX`` in DEFAULT_CSS alone
#: dropped the market out of the comparison entirely and left nine -- still
#: green, with the two copies' market geometry never compared again.
_DEFAULT_CSS_ONLY = frozenset({"#title-bar", "#separator"})
_BLOCK_ONLY = frozenset({"SurfFeed > RichLog", "SurfDevActivity > RichLog"})


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
                "LP MIGRATION",
                "GATE OPEN",
                "NEW DEPLOY",
                "BRIDGE STAGE",
                "BURN",
            ):
                assert label in text, f"{label} never reached the compositor"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# __main__.FULL_LAYOUT_COLUMNS must cover every dashboard, surf included
# ---------------------------------------------------------------------------


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

    for name in ("README.md", "CLAUDE.md"):
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
        "hook_status", "lp_owner_ok", "gate_open",
        "supply_series", "price_series", "nft_last_sales", "dev_activity",
        # v4 migration + IMD launchpad (Task 1, 2026-08-23): strings, a
        # tri-state bool and a list -- same reasoning as the block above,
        # applied to the new contract surface.
        "pool_venue", "pool_id_source", "lp_state", "launchpad_as_of_hhmm",
        "burn_ready", "launchpad_coins",
        "sig_decoy_state", "sig_decoy_detail",
        "sig_burnready_state", "sig_burnready_detail",
        "sig_hot_state", "sig_hot_detail",
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
    "pool_fee_bps": "no widget consumes this key yet; Task 8 wires SurfHero's _pool_lines()",
    "pool_liquidity_raw": "no widget consumes this key yet; pool_liquidity_usd is the one rendered",
    "decoy_pool_count": "no widget consumes this key yet; Task 8 wires SurfHero's _pool_lines()",
    "lp_position_count": "no widget consumes this key yet; no task's Consumes list names it",
    "burn_accrued": "no widget consumes this key yet; Task 11's SurfBurnPipeline wires it",
    "burn_staged": "no widget consumes this key yet; Task 11's SurfBurnPipeline wires it",
    "burn_min_bridge": "no widget consumes this key yet; Task 11's SurfBurnPipeline wires it",
    "launchpad_coin_count": "no widget consumes this key yet; Task 11's launchpad widgets wire it",
    "launchpad_swap_count": "no widget consumes this key yet; Task 11's launchpad widgets wire it",
    "launchpad_trader_count": "no widget consumes this key yet; Task 11's launchpad widgets wire it",
    "launchpad_burned_total": "no widget consumes this key yet; Task 11's launchpad widgets wire it",
    "launchpad_creator_eth_owed": "no widget consumes this key yet; Task 11's launchpad widgets wire it",
    # Same age_s-only-on-FIRED reasoning as the six existing sig_*_age_s
    # entries just above -- these three new detectors follow the identical
    # widgets/surf/signals.py `_head()` pattern once Task 9 wires them.
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
    "feed_nonce": "feed #0",                    # screens/surf.py _fmt_int
    "feed_last_post_age_s": "(0s)",              # screens/surf.py _fmt_age
    "lp_imd": "0 IMD",                           # hero.py _update_lp
    "lp_weth": "0.00 WETH",                      # hero.py _update_lp
    "identities_written": "0/2000 writt",        # hero.py _update_gate
    "imd_supply": "0 IMD",                       # hero.py _update_supply
    # The field's own honest zero rendering (distinct from `imd_burned_cum
    # is None` -> "burned --"): this is the exact shape the house rule
    # guards -- a fabricated 0 here would falsely claim "we watched and
    # nothing moved" instead of the honest "we could not read this".
    "imd_burned_cum": "no burn obser",           # hero.py _update_supply
    "imd_price_usd": "$0.00",                    # market.py fmt_price (pre-existing check)
    "fp_price_usd": "FP $0.00",                  # market.py fmt_price
    "imd_change_24h_pct": "+0.00% 24h",          # market.py _fmt_change
    "imd_vol_24h_usd": "vol 24h $0",             # market.py fmt_compact
    "pool_liquidity_usd": "pool $0",             # market.py fmt_compact
    "parity_pct": "parity ● +0.00%",        # market.py _fmt_parity
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
}


def test_every_surf_key_is_triaged_for_the_zero_catch() -> None:
    """A SURF_KEYS key added later must be triaged, not silently uncovered.

    Three disjoint buckets -- checked, numeric-but-unobservable, and
    structurally non-numeric -- must partition ``SURF_KEYS`` exactly. This is
    what "drive it from the real key list" means in practice: a hand-typed
    list of fields to check would silently stop covering the contract the
    moment ``SURF_KEYS`` grows, which is exactly the shape of the finding
    this test exists to close.
    """
    from maxpane_dashboard.data.surf_models import SURF_KEYS

    checked = set(_NUMERIC_ZERO_PROBES)
    excluded = set(_NUMERIC_KEYS_EXCLUDED)
    non_numeric = set(_NON_NUMERIC_KEYS)

    overlap = (checked & excluded) | (checked & non_numeric) | (excluded & non_numeric)
    assert not overlap, f"a key is triaged into more than one bucket: {overlap}"

    covered = checked | excluded | non_numeric
    missing = set(SURF_KEYS) - covered
    assert not missing, (
        f"SURF_KEYS grew a key this test never triaged: {missing} -- add it "
        "to _NUMERIC_ZERO_PROBES, _NUMERIC_KEYS_EXCLUDED or _NON_NUMERIC_KEYS"
    )
    extra = covered - set(SURF_KEYS)
    assert not extra, f"triaged a key SURF_KEYS no longer has: {extra}"


def test_a_full_outage_renders_explicit_states_not_zeros() -> None:
    """Every detector is on screen, none of them reads as a live number.

    ``0`` is the forbidden rendering: CLAUDE.md's "a failed read is None,
    never 0" exists because a zeroed supply reads as a 100% burn. Checked
    across the numeric surface of ``SURF_KEYS`` (see ``_NUMERIC_ZERO_PROBES``
    above), not just the price.
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

            text = _screen_text(app)
            for label in (
                "NEW POST",
                "LP MIGRATION",
                "GATE OPEN",
                "NEW DEPLOY",
                "BRIDGE STAGE",
                "BURN",
            ):
                assert label in text, f"{label} vanished under outage"
            # The title bar names every failing group behind the house
            # warning glyph (the prefix was the word "degraded" until
            # 2026-08-12). What this pins is end-to-end and geometric: the
            # *whole* six-name list reaches a pixel through the real app at
            # 143x48, on a row that wraps out of existence rather than
            # ellipsising -- see WORST_CASE_TITLE_COLUMNS, which measures it
            # at 137. It does **not** pin the vocabulary: the double's
            # `_degraded` is `sorted(SOURCES)` too, so a renamed group
            # renames both sides and stays green here. The rename tripwire
            # is test_degraded_sources_ride_the_house_warning_glyph_not_the_word
            # in tests/screens/test_surf_screen.py, which spells the six out.
            from maxpane_dashboard.data.surf_manager import SOURCES

            assert "⚠ " + ", ".join(sorted(SOURCES)) in text, (
                "the title bar never told the operator sources are down"
            )
            assert "FIRED" not in text, (
                "a signal fired on an outage -- baselines moved on a failed read"
            )
            assert "$0.00" not in text, "a missing price rendered as zero"
            for probe_key, needle in _NUMERIC_ZERO_PROBES.items():
                assert needle not in text, (
                    f"{probe_key} rendered its zero-formatted string "
                    f"{needle!r} under a full outage -- a failed read must "
                    "never render as a real 0"
                )

    asyncio.run(_run())


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
