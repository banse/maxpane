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
    "Mission Control",
    "surfsurf.eth announce channel + launch detectors on Ethereum",
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
            assert SURF_ROW[2] in text          # Mission Control
            assert "announce channel" in text   # from the description

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

    ``#hero-row`` is ten rows and SurfSignals fills them with a title plus six
    detector rows inside a border.  A vertical pad here clips the sixth row --
    the BURN detector -- exactly the way ``padding: 1 2`` clipped the FWA
    coverage badge.  Horizontal padding (``0 1``, ``0 2``) is fine.
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
                "sixth detector row"
            )


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


def test_a_full_outage_renders_explicit_states_not_zeros() -> None:
    """Every detector is on screen, none of them reads as a live number.

    ``0`` is the forbidden rendering: CLAUDE.md's "a failed read is None,
    never 0" exists because a zeroed supply reads as a 100% burn.
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

    asyncio.run(_run())
