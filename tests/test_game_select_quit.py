"""LOW-19: quitting from the game-select menu must shut down gracefully.

``GameSelectScreen.on_key`` handled ``q`` itself and called
``self.app.exit()``.  That bypasses ``MaxPaneApp.action_quit`` entirely, so
no manager's ``close()`` was ever awaited:

* every manager's ``httpx.AsyncClient`` was abandoned at event-loop teardown
  rather than closed;
* ``save_cache()`` never ran, so the session's history (bakery, frenpet,
  ocm, dota, ttt, ...) was thrown away.

Quitting from a dashboard went through the app-level ``q`` binding and
behaved correctly, so the two quit paths disagreed -- and the menu path is
the one a user reaches by pressing ``m`` then ``q``.

The fix removed the branch so ``q`` bubbles to the app binding.  These tests
therefore assert the *observable* consequence -- ``close()`` was awaited on
every manager -- rather than reading the source, and they assert it after
twenty menu round-trips: a shutdown that fires once per visit, or a menu
that accumulates a screen per visit, is the kind of leak a single-cycle test
cannot see.

Everything runs headless with zero network: every manager is replaced by a
stub before ``run_test()``.
"""

from __future__ import annotations

import asyncio
import gc
from typing import Any

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen

#: Attribute names of every manager the app builds in ``__init__``.
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
]

#: A game whose screen mounts without a wallet or any network call.
_GAME = "base"
_GAME_KEY = next(key for key, gid, *_ in GAMES if gid == _GAME)


class CountingManager:
    """Manager that records how many times it was closed."""

    def __init__(self) -> None:
        self._error_count = 0
        self.closed = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        return {}

    async def close(self) -> None:
        self.closed += 1


def _make_app() -> tuple[MaxPaneApp, dict[str, CountingManager]]:
    app = MaxPaneApp(initial_game=_GAME)
    stubs: dict[str, CountingManager] = {}
    for attr in MANAGER_ATTRS:
        stub = CountingManager()
        stubs[attr] = stub
        setattr(app, attr, stub)
    return app, stubs


def _live_menu_screens() -> int:
    """How many ``GameSelectScreen`` objects the interpreter still holds."""
    gc.collect()
    return sum(1 for obj in gc.get_objects() if isinstance(obj, GameSelectScreen))


# ---------------------------------------------------------------------------
# the leak
# ---------------------------------------------------------------------------


def test_quitting_from_the_menu_closes_every_manager() -> None:
    """``m`` then ``q`` must run the same shutdown as ``q`` on a dashboard.

    Before the fix every count here was 0: the app exited without awaiting
    a single ``close()``.
    """

    async def _run() -> None:
        app, stubs = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")  # dismiss splash
            await pilot.pause()
            await pilot.press(_GAME_KEY)  # open a dashboard
            await pilot.pause()
            await pilot.press("m")  # back to the menu
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)

            await pilot.press("q")
            await pilot.pause()

            for attr, stub in stubs.items():
                assert stub.closed == 1, (
                    f"{attr}.close() ran {stub.closed} times on quit-from-menu; "
                    "the graceful shutdown was skipped or ran twice"
                )
            assert app._exception is None
            assert not app.is_running

    asyncio.run(_run())


def test_menu_and_dashboard_quit_paths_agree() -> None:
    """The two ways out of the app must do the same thing.

    Quitting from a dashboard always worked; this pins the menu path to it
    so they cannot drift apart again.
    """

    async def _quit_from(where: str) -> dict[str, int]:
        app, stubs = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(_GAME_KEY)
            await pilot.pause()
            if where == "menu":
                await pilot.press("m")
                await pilot.pause()
                assert isinstance(app.screen, GameSelectScreen)
            else:
                assert not isinstance(app.screen, GameSelectScreen)
            await pilot.press("q")
            await pilot.pause()
        return {attr: stub.closed for attr, stub in stubs.items()}

    from_menu = asyncio.run(_quit_from("menu"))
    from_dashboard = asyncio.run(_quit_from("dashboard"))

    assert from_menu == from_dashboard, (
        "quitting from the menu shuts down differently than quitting from a "
        f"dashboard: {from_menu} vs {from_dashboard}"
    )
    assert all(count == 1 for count in from_dashboard.values())


# ---------------------------------------------------------------------------
# the lifecycle: the menu is entered and left over and over
# ---------------------------------------------------------------------------


def test_repeated_menu_visits_do_not_accumulate_resources() -> None:
    """Twenty ``m`` -> select round-trips must leave the app the same size.

    A per-visit leak is invisible in a one-cycle test.  Screen stack depth,
    installed screens and live ``GameSelectScreen`` objects are all pinned,
    and the shutdown afterwards must still close each manager exactly once
    -- not once per visit.
    """

    async def _run() -> None:
        app, stubs = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(_GAME_KEY)
            await pilot.pause()

            baseline = (
                len(app.screen_stack),
                len(app._installed_screens),
                _live_menu_screens(),
            )

            for visit in range(20):
                await pilot.press("m")
                await pilot.pause()
                assert isinstance(app.screen, GameSelectScreen), visit
                await pilot.press(_GAME_KEY)
                await pilot.pause()
                assert not isinstance(app.screen, GameSelectScreen), visit

            after = (
                len(app.screen_stack),
                len(app._installed_screens),
                _live_menu_screens(),
            )
            assert after == baseline, (
                "20 menu visits changed the app's resource footprint "
                f"(stack, installed, live menu screens): {baseline} -> {after}"
            )
            assert app._exception is None

            # And the shutdown still runs exactly once.
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            for attr, stub in stubs.items():
                assert stub.closed == 1, f"{attr} closed {stub.closed} times"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# no regression: the menu still selects games
# ---------------------------------------------------------------------------


def test_number_keys_still_select_a_game() -> None:
    """Removing the ``q`` branch must not disturb selection."""

    async def _run() -> None:
        app, _stubs = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press(_GAME_KEY)
            await pilot.pause()

            assert app.screen.name == _GAME
            assert app._exception is None
            assert app.is_running

    asyncio.run(_run())


def test_unbound_keys_on_the_menu_do_nothing() -> None:
    """A stray keystroke must neither select nor quit."""

    async def _run() -> None:
        app, stubs = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            for key in ("z", "x", "0"):
                await pilot.press(key)
                await pilot.pause()

            assert isinstance(app.screen, GameSelectScreen)
            assert app.is_running
            assert all(stub.closed == 0 for stub in stubs.values())
            assert app._exception is None

    asyncio.run(_run())
