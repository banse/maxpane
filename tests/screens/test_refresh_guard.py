"""Concurrency tests for the shared screen refresh guard (MEDI-34 / MEDI-35).

**Zero network, zero sleeps.**  Both races are reproduced with an
``asyncio.Event``-driven manager double: the test blocks *inside*
``fetch_and_compute`` until it chooses to release it, so the interleaving is
chosen by the test rather than by the clock.  The only ``asyncio.sleep`` in this
file is ``sleep(0)`` — a bare event-loop yield used to give every runnable task
its turn, not a delay.  A ``sleep(0.05)`` here would pass on a fast machine and
flake on CI, which for a race test is worse than having no test at all.

Both tests are mutation-checked: each fails against the pre-fix code (see the
module docstring of :mod:`maxpane_dashboard.screens.refresh_guard` for what the
pre-fix code was).

* :func:`test_overrun_tick_is_skipped_never_cancels_the_refresh` fails if
  ``RefreshGuard.start_refresh`` stops checking ``_refresh_in_flight``
  (``manager.calls == 2``, ``cancelled == 1``, ``completed == 0`` — the
  livelock).
* :func:`test_screen_refresh_joins_the_startup_prefetch` fails if
  ``_guarded_refresh`` stops awaiting ``_await_startup_prefetch``
  (``max_concurrent == 2`` — two ``fetch_and_compute`` calls on one manager,
  which is how the event watermark gets double-applied).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest
from textual.app import App
from textual.screen import Screen

import maxpane_dashboard.screens as screens_pkg
from maxpane_dashboard.screens.refresh_guard import PREFETCH_WORKER_NAME, RefreshGuard
from maxpane_dashboard.screens.talismans import TalismansScreen
from maxpane_dashboard.screens.ttt import TTTScreen

REPO = Path(__file__).resolve().parents[2]
SCREENS_DIR = REPO / "maxpane_dashboard" / "screens"
TEMPLATE = REPO / "maxpane_dashboard" / "templates" / "screen_template.py"


async def _drain(iterations: int = 200) -> None:
    """Let every currently-runnable task run to its next await point.

    Not a delay: ``sleep(0)`` yields to the event loop and comes straight back.
    Repeated, it exhausts the ready queue, so anything that *would* have run
    concurrently has run by the time the assertions execute.
    """
    for _ in range(iterations):
        await asyncio.sleep(0)


class _BlockingManager:
    """Manager double that parks inside ``fetch_and_compute`` until released.

    Records everything the two races are visible in: how many fetches were
    started, the high-water mark of *simultaneous* fetches, how many finished,
    and how many were cancelled mid-flight.
    """

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.completed = 0
        self.cancelled = 0
        self.concurrent = 0
        self.max_concurrent = 0
        self.fail_next = False

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.entered.set()
        try:
            await self.release.wait()
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("simulated RPC failure")
            self.completed += 1
            # The screens defend every widget update with try/except and read
            # the payload with .get(), so an empty dict exercises the dispatch
            # path without needing the full data contract.
            return {}
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.concurrent -= 1

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


class _ScreenHarness(App):
    """Push one dashboard screen, nothing else."""

    def __init__(self, screen: Screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _PrefetchHarness(App):
    """Reproduces ``MaxPaneApp.on_mount``'s startup prefetch, exactly.

    Same worker name, same node (the app), same ``exclusive=True``, same
    swallow-everything body.  The screen is *not* pushed here — the test pushes
    it once the prefetch is provably inside ``fetch_and_compute``, which is the
    ordering the real app produces (prefetch starts at ``on_mount``, the
    dashboard screen appears only after splash + game select).
    """

    def __init__(self, manager: _BlockingManager) -> None:
        super().__init__()
        self._manager = manager

    def on_mount(self) -> None:
        self.run_worker(
            self._prefetch(),
            exclusive=True,
            name=PREFETCH_WORKER_NAME,
            exit_on_error=False,
        )

    async def _prefetch(self) -> None:
        try:
            await self._manager.fetch_and_compute()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MEDI-34 -- interval overrun must skip, never cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overrun_tick_is_skipped_never_cancels_the_refresh():
    """A poll tick arriving mid-refresh is dropped; the refresh survives.

    Pre-fix, ``_schedule_refresh`` called ``run_worker(..., exclusive=True)``
    unconditionally, and Textual cancels the same node+group — so the tick
    killed the in-flight refresh and started it from scratch.  Under sustained
    RPC degradation every cycle overruns, so every cycle is killed at the same
    point: the screen never renders.
    """
    manager = _BlockingManager()
    screen = TalismansScreen(manager, poll_interval=30, name="talismans")
    app = _ScreenHarness(screen)

    async with app.run_test():
        # on_screen_resume already fired the initial refresh; wait until it is
        # provably parked inside fetch_and_compute.
        await manager.entered.wait()
        assert manager.calls == 1
        assert manager.concurrent == 1

        # Two poll ticks land while that refresh is still running.
        screen._schedule_refresh()
        screen._schedule_refresh()
        await _drain()

        # Skipped, never queued -- and, crucially, the in-flight refresh was
        # neither cancelled nor restarted.
        assert manager.calls == 1, "an overrun tick started a second fetch"
        assert manager.cancelled == 0, "an overrun tick cancelled the in-flight refresh"
        assert screen._refresh_skipped == 2

        # The refresh that was allowed to keep running completes normally.
        manager.release.set()
        await _drain()
        assert manager.completed == 1
        assert screen._refresh_in_flight is False

        # And the screen is not wedged: the next tick starts a fresh cycle.
        manager.entered.clear()
        screen._schedule_refresh()
        await _drain()
        assert manager.calls == 2


@pytest.mark.asyncio
async def test_failed_refresh_lowers_the_in_flight_flag():
    """A refresh that raises must not wedge the screen on placeholders forever."""
    manager = _BlockingManager()
    screen = TalismansScreen(manager, poll_interval=30, name="talismans")
    app = _ScreenHarness(screen)

    async with app.run_test():
        await manager.entered.wait()
        manager.fail_next = True
        manager.release.set()
        await _drain()

        assert manager.calls == 1
        assert screen._refresh_in_flight is False

        manager.entered.clear()
        screen._schedule_refresh()
        await _drain()
        assert manager.calls == 2


# ---------------------------------------------------------------------------
# MEDI-35 -- the screen's first refresh must not race the startup prefetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_refresh_joins_the_startup_prefetch():
    """Only one ``fetch_and_compute`` runs on a manager at a time.

    Pre-fix, the app-node prefetch and the screen-node initial refresh both ran
    ``fetch_and_compute`` on the same manager: ``exclusive=True`` only cancels
    within one node, so the screen's worker could not displace the app's.  Both
    first-run log scans then read the same ``last_seen_block == 0`` and both
    applied every event.
    """
    manager = _BlockingManager()
    app = _PrefetchHarness(manager)
    screen = TTTScreen(manager, poll_interval=30, name="ttt")

    async with app.run_test():
        # The prefetch is parked inside fetch_and_compute.
        await manager.entered.wait()
        assert manager.calls == 1

        # The dashboard screen appears while the prefetch is still running.
        app.push_screen(screen)
        await _drain()

        # The screen joined instead of racing: still exactly one fetch.
        assert manager.max_concurrent == 1, (
            "screen refresh ran concurrently with the startup prefetch"
        )
        assert manager.calls == 1

        # Once the prefetch finishes, the screen's own fetch proceeds -- serially.
        manager.release.set()
        await _drain()
        assert manager.calls == 2
        assert manager.max_concurrent == 1
        assert manager.completed == 2


@pytest.mark.asyncio
async def test_prefetch_failure_does_not_block_the_screen():
    """A prefetch that blows up must not stop the screen from fetching."""
    manager = _BlockingManager()
    app = _PrefetchHarness(manager)
    screen = TalismansScreen(manager, poll_interval=30, name="talismans")

    async with app.run_test():
        await manager.entered.wait()
        manager.fail_next = True
        app.push_screen(screen)
        await _drain()
        manager.release.set()
        await _drain()

        assert manager.calls == 2  # prefetch raised, screen still fetched
        assert manager.max_concurrent == 1


# ---------------------------------------------------------------------------
# The pattern must not come back -- structural checks over every screen
# ---------------------------------------------------------------------------


def _dashboard_screen_classes() -> list[type]:
    """Every Screen subclass in the package that polls a manager."""
    found: list[type] = []
    for mod_info in pkgutil.iter_modules(screens_pkg.__path__):
        module = importlib.import_module(f"{screens_pkg.__name__}.{mod_info.name}")
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, Screen)
                and obj.__module__ == module.__name__
                and "_do_refresh" in vars(obj)
            ):
                found.append(obj)
    return found


def test_every_polling_screen_uses_the_guard():
    """A screen that polls must inherit the guard, not hand-roll scheduling."""
    classes = _dashboard_screen_classes()
    # bakery, base, cattown, dota, frenpet x4, fwa, ocm, talismans, ttt
    assert len(classes) >= 12, f"expected >=12 dashboard screens, found {classes}"

    for cls in classes:
        assert issubclass(cls, RefreshGuard), f"{cls.__name__} does not use RefreshGuard"
        assert cls.REFRESH_WORKER_NAME != RefreshGuard.REFRESH_WORKER_NAME, (
            f"{cls.__name__} must set its own REFRESH_WORKER_NAME"
        )
        for meth in ("_do_initial_refresh", "_schedule_refresh", "action_refresh"):
            assert meth not in vars(cls), (
                f"{cls.__name__} overrides {meth}; scheduling belongs to RefreshGuard"
            )
            assert getattr(cls, meth) is getattr(RefreshGuard, meth)


def test_no_screen_schedules_a_bare_refresh_worker():
    """The exact pre-fix line must not reappear -- including in the template.

    ``templates/screen_template.py`` is the copy-source for new dashboards, so
    a copy of the race living there reintroduces it in dashboard number
    thirteen no matter how many instances were fixed.
    """
    bare = re.compile(r"run_worker\(\s*self\._do_refresh\(\)")
    offenders = []
    for path in sorted(SCREENS_DIR.glob("*.py")) + [TEMPLATE]:
        if path.name == "refresh_guard.py":
            continue  # documents the old line in its docstring, by design
        if bare.search(path.read_text()):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"bare refresh worker (MEDI-34/35 pattern) in: {offenders}"


def test_template_screen_inherits_the_guard():
    """New dashboards are seeded from the template; it must carry the fix."""
    template = importlib.import_module("maxpane_dashboard.templates.screen_template")
    seeds = [
        obj
        for obj in vars(template).values()
        if inspect.isclass(obj)
        and issubclass(obj, Screen)
        and obj.__module__ == template.__name__
    ]
    assert seeds, "screen_template.py exposes no Screen subclass"
    for cls in seeds:
        assert issubclass(cls, RefreshGuard)
        assert cls.REFRESH_WORKER_NAME != RefreshGuard.REFRESH_WORKER_NAME
