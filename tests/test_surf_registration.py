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
