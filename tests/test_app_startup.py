"""Startup-resilience tests for ``MaxPaneApp`` (HIGH-2, MEDI-9, MEDI-10/11).

Everything here runs headless with **zero network**: every manager on the app
is replaced by a stub before ``run_test()``, so no HTTP client is ever used.

HIGH-2 -- the ``on_mount`` prefetch worker used to run
``manager.fetch_and_compute()`` with ``run_worker``'s default
``exit_on_error=True`` and no guard, so a launch-time fetch failure (no
network, DNS failure, game API 5xx) panicked Textual with ``WorkerFailed`` and
killed the process with return code 1 instead of showing the dashboard.  The
tests below launch every ``--game`` choice with a manager that raises and
assert the app is still standing.

MEDI-9 -- ``tab`` was shadowed by Screen's built-in ``tab -> focus_next``, so
game cycling never ran despite being advertised in the UI hints.

MEDI-10/11 -- the four FrenPetManager instances share one cache file and
``save_to_file`` is a full overwrite, so the idle managers used to discard the
active manager's session history on quit.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import pytest

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.bakery import BakeryScreen
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen

#: Every ``--game`` choice, including the ones hidden from the select screen.
ALL_GAMES = [
    "bakery",
    "frenpet",
    "frenpet_full",
    "frenpet_wallet",
    "frenpet_perf",
    "base",
    "cattown",
    "ocm",
    "dota",
    "ttt",
    "talismans",
    "fwa",
]

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


class BoomManager:
    """Manager whose every fetch fails, the way an offline launch fails."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("no network")
        self._error_count = 1
        self.calls = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        raise self._exc

    async def close(self) -> None:
        return None


def _make_app(game: str) -> MaxPaneApp:
    """Build the app with every manager replaced by a failing stub."""
    app = MaxPaneApp(initial_game=game)
    for attr in MANAGER_ATTRS:
        setattr(app, attr, BoomManager())
    return app


# ---------------------------------------------------------------------------
# HIGH-2: a failing startup prefetch must not kill the app
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game", ALL_GAMES)
def test_failing_prefetch_does_not_kill_app(game: str) -> None:
    """Every --game choice survives a manager that raises at launch."""

    async def _run() -> None:
        app = _make_app(game)
        async with app.run_test() as pilot:
            await pilot.pause()
            # The prefetch actually ran and actually failed ...
            manager = app._prefetch_manager(game)
            assert isinstance(manager, BoomManager)
            assert manager.calls >= 1, "prefetch never ran for %s" % game
            # ... and the app is still alive with a screen on stack.
            assert app._exception is None, f"{game}: {app._exception!r}"
            assert app.screen is not None
            assert app.is_running
        assert app.return_code != 1, f"{game}: exited with return code 1"

    asyncio.run(_run())


def test_failing_prefetch_still_reaches_the_dashboard() -> None:
    """Offline launch of the default game reaches a usable BakeryScreen.

    Splash -> game select -> bakery dashboard, with the bakery manager raising
    on every fetch.  Before the fix this never got past ``on_mount``: the
    prefetch worker raised ``WorkerFailed`` while the splash was showing.
    """
    bakery_key = next(key for key, gid, *_ in GAMES if gid == "bakery")

    async def _run() -> None:
        app = _make_app("bakery")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")  # dismiss splash
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press(bakery_key)  # choose Rugpull Bakery
            await pilot.pause()

            assert app._exception is None
            assert isinstance(app.screen, BakeryScreen)
            assert app.screen.name == "bakery"
            # The screen's own refresh also failed and was swallowed, so the
            # dashboard is up with an error status rather than gone.
            assert app._bakery_manager.calls >= 2
        assert app.return_code != 1

    asyncio.run(_run())


def test_prefetch_swallows_errors_but_returns_data_on_success() -> None:
    """The guard logs failures and stays out of the way when fetches work."""

    class _OKManager(BoomManager):
        async def fetch_and_compute(self) -> dict[str, Any]:
            self.calls += 1
            return {"ok": True}

    app = MaxPaneApp(initial_game="bakery")
    ok = _OKManager()
    boom = BoomManager()

    asyncio.run(app._prefetch(ok, "bakery"))
    assert ok.calls == 1
    # Must not raise -- this is the whole fix.
    asyncio.run(app._prefetch(boom, "bakery"))
    assert boom.calls == 1


def test_every_game_choice_has_a_prefetch_manager() -> None:
    """No --game choice may silently fall through without a prefetch."""
    app = MaxPaneApp()
    for game in ALL_GAMES:
        assert app._prefetch_manager(game) is not None, game
    assert app._prefetch_manager("does-not-exist") is None
    # Every game offered on the select screen is covered too.
    for _key, game_id, *_ in GAMES:
        assert app._prefetch_manager(game_id) is not None, game_id


# ---------------------------------------------------------------------------
# MEDI-9: tab cycles games instead of moving focus
# ---------------------------------------------------------------------------


def test_tab_cycles_games_on_a_dashboard() -> None:
    """Tab on a dashboard runs action_switch_game (was: focus_next)."""
    bakery_key = next(key for key, gid, *_ in GAMES if gid == "bakery")

    async def _run() -> None:
        app = _make_app("bakery")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(bakery_key)
            await pilot.pause()
            assert isinstance(app.screen, BakeryScreen)

            # Record the switch instead of mounting the next dashboard (which
            # would spin up a real manager's poll timer).
            launched: list[str] = []
            app._launch_game = lambda game_id, **kw: launched.append(game_id)

            await pilot.press("tab")
            await pilot.pause()

            expected = MaxPaneApp._GAME_CYCLE[
                (MaxPaneApp._GAME_CYCLE.index("bakery") + 1)
                % len(MaxPaneApp._GAME_CYCLE)
            ]
            assert launched == [expected]
            assert app._current_game == expected

    asyncio.run(_run())


def test_tab_does_not_cycle_games_off_a_dashboard() -> None:
    """On splash / game select, tab keeps its normal focus behaviour."""

    async def _run() -> None:
        app = _make_app("bakery")
        async with app.run_test() as pilot:
            await pilot.pause()
            launched: list[str] = []
            app._launch_game = lambda game_id, **kw: launched.append(game_id)

            await pilot.press("tab")  # on the splash
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press("tab")  # on game select
            await pilot.pause()

            assert launched == []
            assert app._current_game == "bakery"
            assert isinstance(app.screen, GameSelectScreen)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# MEDI-10 / MEDI-11: the idle FrenPet managers must not clobber the cache
# ---------------------------------------------------------------------------


def test_frenpet_managers_share_one_cache(tmp_path, monkeypatch) -> None:
    """A session's history survives the quit-time save of the idle managers."""
    from maxpane_dashboard.data import frenpet_manager as fm
    from maxpane_dashboard.data.frenpet_cache import FrenPetCache

    cache_file = tmp_path / "frenpet_cache.json"
    monkeypatch.setattr(fm, "_CACHE_FILE", cache_file)

    app = MaxPaneApp()
    managers = [
        app._frenpet_manager,
        app._frenpet_full_manager,
        app._frenpet_wallet_manager,
        app._frenpet_perf_manager,
    ]
    for other in managers[1:]:
        assert other.cache is managers[0].cache

    # A session's worth of pet-score history on the only manager that polls
    # (same structure FrenPetCache.update fills, and the only state
    # save_to_file persists).
    live = app._frenpet_manager.cache
    live._pet_histories[7] = deque([(1234.0, 99.0)], maxlen=120)

    # action_quit's order: active manager first, then the three idle ones.
    for manager in managers:
        manager.save_cache()

    reloaded = FrenPetCache(max_history=120)
    reloaded.load_from_file(str(cache_file))
    assert reloaded.get_pet_score_history(7) == [(1234.0, 99.0)], (
        "the idle managers clobbered the session's history on quit"
    )
