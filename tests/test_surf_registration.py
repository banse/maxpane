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
from pathlib import Path
from typing import Any

import pytest

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen

REPO = Path(__file__).resolve().parents[1]

#: The one menu row this WP adds, asserted verbatim so the copy cannot drift.
SURF_ROW = (
    "7",
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


def test_the_default_game_is_still_fwa(monkeypatch) -> None:
    """CLAUDE.md pins fwa as position 1 *and* the ``--game`` default.

    Adding a dashboard must never move it: hiding or displacing the default
    silently breaks launch, which is why this assertion sits next to the one
    that adds surf.
    """
    captured = _run_cli(monkeypatch, [])
    assert captured["initial_game"] == "fwa"


def test_a_typo_is_still_rejected(monkeypatch) -> None:
    """The choices list stays a whitelist -- ``--game surfs`` must exit 2."""
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--game", "surfs"])


# ---------------------------------------------------------------------------
# game_select.py: the menu row -- the surface a user actually presses
# ---------------------------------------------------------------------------


def test_surf_is_menu_entry_seven() -> None:
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


def test_pressing_seven_opens_the_surf_dashboard() -> None:
    """The whole path: splash -> menu -> the key the row advertises.

    The key is read out of ``GAMES`` rather than typed as "7", so a future
    reorder moves this test with the menu instead of breaking it.
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
    """The row reaches the compositor -- not merely the GAMES list."""

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            text = _screen_text(app)
            assert "[7]" in text
            assert SURF_ROW[2] in text          # Surfboard
            assert "onchain adventures" in text  # from the description

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
    import importlib.util

    from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS

    path = REPO / "tests" / "screens" / "test_surf_screen.py"
    spec = importlib.util.spec_from_file_location("_surf_screen_harness", path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

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
    """Splash -> menu -> [7] with the surf manager down: degraded, not dead."""
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
    "nft_dev_holdings": "dev holds 0",           # nft.py _fmt_count
    "nft_written": "identities 0/2000 written",  # nft.py update_data
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
            assert "degraded" in text.lower(), (
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
