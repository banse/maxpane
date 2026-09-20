"""The shared dashboard lifecycle and PANELS dispatch (``screens/dashboard_screen.py``).

Two kinds of test live here.

*Behaviour*, on a minimal subclass declared in this file: resume starts the
timer and primes the status bar, suspend stops it, a failed fetch degrades (and
does not raise on a manager with no ``_error_count`` -- the defect bakery and
frenpet carried), one panel that raises does not stop the next, and the status
bar falls back to the screen's own poll interval.

*Agreement*, over the real screens:
:func:`test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords`
is what replaces 151 hand-typed dispatch blocks. It mounts every
:class:`DashboardScreen` subclass that inherits the refresh and reads its
``PANELS`` against ``compose`` and against each widget's real ``update_data``
signature, in both directions -- so a mistyped key, a dropped row and a widget
that is not in ``compose`` each redden a named test rather than silently
blanking a panel.

No network: the sweep's own fake managers and payloads are reused where a case
exists, and a ``{}``-payload manager otherwise.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil

import pytest
from textual.app import App
from textual.widgets import Static

import maxpane_dashboard.screens as screens_pkg
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.address_sweep.builders import _PayloadManager
from tests.address_sweep.registry import CASES

# ---------------------------------------------------------------------------
# A minimal subclass: two panels, a title bar and a status bar
# ---------------------------------------------------------------------------


class _FirstPanel(Static):
    """Records what the dispatch handed it."""

    def __init__(self, **kwargs) -> None:
        super().__init__("first", **kwargs)
        self.seen: dict | None = None

    def update_data(self, alpha=None, beta="") -> None:
        self.seen = {"alpha": alpha, "beta": beta}


class _BoomPanel(Static):
    """Raises out of ``update_data``, the way a real panel does on bad data."""

    def __init__(self, **kwargs) -> None:
        super().__init__("boom", **kwargs)

    def update_data(self, gamma=None) -> None:
        raise RuntimeError("panel exploded")


class _LastPanel(Static):
    """Mounted after ``_BoomPanel``: proves one failure does not stop the next."""

    def __init__(self, **kwargs) -> None:
        super().__init__("last", **kwargs)
        self.seen: dict | None = None

    def update_data(self, delta=None) -> None:
        self.seen = {"delta": delta}


class _MiniScreen(DashboardScreen):
    GAME_NAME = "mini game"
    REFRESH_WORKER_NAME = "mini-refresh"
    PANELS = (
        (_FirstPanel, keys("alpha", "beta", beta="fallback")),
        (_BoomPanel, keys("gamma")),
        (_LastPanel, keys("delta")),
    )

    def __init__(self, manager, **kwargs) -> None:
        super().__init__(manager, **kwargs)
        self.primed_with: StatusBar | None = None
        self.titled_with: dict | None = None
        self.title_raises = False

    def compose(self):
        yield Static("mini · title", id="title-bar")
        yield _FirstPanel()
        yield _BoomPanel()
        yield _LastPanel()
        yield StatusBar()

    def _prime_status_bar(self, bar: StatusBar) -> None:
        self.primed_with = bar

    def _update_title(self, data: dict) -> None:
        self.titled_with = data
        if self.title_raises:
            raise RuntimeError("title exploded")


class _FakeManager:
    """Serves one payload, or raises. Never touches the network."""

    def __init__(self, payload: dict | None = None, *, fail=False, error_count=0) -> None:
        self._payload = payload if payload is not None else {}
        self._error_count = error_count
        self.fail = fail
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self.fail:
            self._error_count += 1
            raise RuntimeError("network down")
        return dict(self._payload)

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


class _Harness(App):
    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _status_left(screen) -> str:
    widget = screen.query_one(StatusBar).query_one("#status-left", Static)
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


def _status_right(screen) -> str:
    widget = screen.query_one(StatusBar).query_one("#status-right", Static)
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


# ---------------------------------------------------------------------------
# keys()
# ---------------------------------------------------------------------------


def test_keys_reads_data_get_with_the_given_defaults_and_nothing_else():
    adapt = keys("alpha", "beta", beta="fallback")

    assert adapt({"alpha": 1, "beta": 2}) == {"alpha": 1, "beta": 2}
    # A key with a default falls back to it; a key without one reads as None,
    # never 0 (the "a failed read is None" convention).
    assert adapt({}) == {"alpha": None, "beta": "fallback"}
    # Nothing the panel did not ask for leaks through.
    assert adapt({"alpha": 1, "extra": "x"}) == {"alpha": 1, "beta": "fallback"}
    # An explicit None in the payload is a value, not a missing key.
    assert adapt({"alpha": None, "beta": None}) == {"alpha": None, "beta": None}


def test_keys_refuses_a_default_that_names_no_key():
    """``faucet_opn=True`` beside ``"faucet_open"`` would silently send None."""
    with pytest.raises(ValueError, match="faucet_opn"):
        keys("faucet_open", faucet_opn=True)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_starts_the_timer_and_primes_the_status_bar():
    screen = _MiniScreen(_FakeManager(), poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert screen._refresh_timer is not None, "resume did not start the poll timer"
        right = _status_right(screen)
        assert "mini game" in right, right
        assert app.theme in right, right


@pytest.mark.asyncio
async def test_resume_calls_the_prime_status_bar_hook_with_the_bar():
    screen = _MiniScreen(_FakeManager(), poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen.primed_with is screen.query_one(StatusBar)


@pytest.mark.asyncio
async def test_suspend_stops_the_timer():
    screen = _MiniScreen(_FakeManager(), poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        timer = screen._refresh_timer
        assert timer is not None

        screen.on_screen_suspend()
        await pilot.pause()

        assert screen._refresh_timer is None, "suspend left the poll timer set"
        # Timer.stop() drops its task; clearing the attribute without
        # stopping would leave the interval ticking on a suspended screen.
        assert timer._task is None, "the timer was cleared but never stopped"


# ---------------------------------------------------------------------------
# The failure path (ported from test_base_terminal_screen.py:77-110)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_refresh_reports_999_and_the_managers_error_count():
    manager = _FakeManager(fail=True, error_count=2)
    screen = _MiniScreen(manager, poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()  # must not raise
        await pilot.pause()

        assert manager._error_count >= 3
        text = _status_left(screen)
        assert "updated 999s ago" in text, text
        assert f"{manager._error_count} errors" in text, text


@pytest.mark.asyncio
async def test_failed_refresh_tolerates_a_manager_without_error_count():
    """bakery and frenpet read ``_error_count`` bare and raised out of the
    handler that only runs because the fetch had already failed."""

    class _Bare:
        async def fetch_and_compute(self) -> dict:
            raise RuntimeError("boom")

    screen = _MiniScreen(_Bare(), poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()  # must not raise
        await pilot.pause()

        text = _status_left(screen)
        assert "updated 999s ago" in text, text
        assert "errors" not in text, text


# ---------------------------------------------------------------------------
# The dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_panel_that_raises_is_logged_at_warning_and_the_next_still_updates(caplog):
    manager = _FakeManager({"alpha": 7, "gamma": "g", "delta": "d"})
    screen = _MiniScreen(manager, poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        with caplog.at_level(logging.WARNING, logger="maxpane_dashboard.screens.dashboard_screen"):
            await screen._do_refresh()
        await pilot.pause()

        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failed to update _BoomPanel" in m and "panel exploded" in m for m in messages), messages

        # The row before it ran, and -- the point -- the row after it ran too.
        assert screen.query_one(_FirstPanel).seen == {"alpha": 7, "beta": "fallback"}
        assert screen.query_one(_LastPanel).seen == {"delta": "d"}


@pytest.mark.asyncio
async def test_the_status_bar_row_defaults_poll_interval_to_the_screens():
    manager = _FakeManager({"last_updated_seconds_ago": 4, "error_count": 0})
    screen = _MiniScreen(manager, poll_interval=77, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _status_left(screen)
        assert "77s poll" in text, text
        assert "updated 4s ago" in text, text


@pytest.mark.asyncio
async def test_the_status_bar_row_prefers_the_payloads_poll_interval():
    manager = _FakeManager({"last_updated_seconds_ago": 0, "error_count": 0, "poll_interval": 60})
    screen = _MiniScreen(manager, poll_interval=77, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert "60s poll" in _status_left(screen)


@pytest.mark.asyncio
async def test_update_title_receives_the_payload():
    manager = _FakeManager({"season_id": 9})
    screen = _MiniScreen(manager, poll_interval=30, name="mini")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert screen.titled_with == {"season_id": 9}


@pytest.mark.asyncio
async def test_a_raising_update_title_is_contained_and_the_panels_still_update(caplog):
    manager = _FakeManager({"alpha": 3, "delta": "d"})
    screen = _MiniScreen(manager, poll_interval=30, name="mini")
    screen.title_raises = True
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.title_raises = True
        with caplog.at_level(logging.WARNING, logger="maxpane_dashboard.screens.dashboard_screen"):
            await screen._do_refresh()  # must not raise
        await pilot.pause()

        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("title bar" in m and "title exploded" in m for m in messages), messages
        assert screen.query_one(_FirstPanel).seen == {"alpha": 3, "beta": "fallback"}


# ---------------------------------------------------------------------------
# The agreement test: PANELS against compose and against every signature
# ---------------------------------------------------------------------------


def _dispatching_screen_classes() -> list[type]:
    """Every ``DashboardScreen`` subclass in ``screens/`` that inherits ``_do_refresh``.

    A screen that keeps a custom ``_do_refresh`` (surf, curator, fwa,
    frenpet_full) does not dispatch through ``PANELS``, so its rows are not
    this test's business.
    """
    found: list[type] = []
    for mod_info in pkgutil.iter_modules(screens_pkg.__path__):
        module = importlib.import_module(f"{screens_pkg.__name__}.{mod_info.name}")
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, DashboardScreen)
                and obj is not DashboardScreen
                and obj.__module__ == module.__name__
                and "_do_refresh" not in vars(obj)
            ):
                found.append(obj)
    return found


_CASE_BY_CLASS = {case.screen_class: case for case in CASES}


def test_at_least_one_screen_dispatches_through_panels():
    """The parametrised test below is vacuous if the list is empty."""
    classes = _dispatching_screen_classes()
    assert classes, "no DashboardScreen subclass inherits the shared _do_refresh"


def _panel_classes(screen_class) -> list[type]:
    return [widget_class for widget_class, _ in screen_class.PANELS]


def _unclaimed_panels(screen, screen_class) -> list[str]:
    """Mounted widgets with an ``update_data`` that no ``PANELS`` row names.

    This is the direction that catches a *dropped* row: the widget is still in
    ``compose``, still mounted, and simply never updated again. The status bar
    is excluded (``_do_refresh`` always updates it, outside ``PANELS``), and so
    is anything nested inside a panel the rows do name.
    """
    named = tuple(_panel_classes(screen_class))
    unclaimed: list[str] = []
    for widget in screen.walk_children(with_self=False):
        cls = type(widget)
        if not callable(getattr(cls, "update_data", None)):
            continue
        if isinstance(widget, StatusBar) or (named and isinstance(widget, named)):
            continue
        # A sub-widget of a named panel (or of the status bar) is that widget's
        # own business, not a row of its own.
        if any(
            isinstance(a, StatusBar) or (named and isinstance(a, named))
            for a in widget.ancestors
        ):
            continue
        unclaimed.append(f"{cls.__module__}.{cls.__qualname__}")
    return unclaimed


@pytest.mark.parametrize(
    "screen_class",
    _dispatching_screen_classes(),
    ids=lambda cls: cls.__name__,
)
@pytest.mark.asyncio
async def test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords(screen_class):
    case = _CASE_BY_CLASS.get(screen_class)
    if case is not None:
        app, payload = case.build(), case.payload()
    else:
        payload = {}
        app = _Harness(screen_class(_PayloadManager(payload), poll_interval=30, name="agreement"))

    async with app.run_test(size=(170, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, screen_class), (type(screen), screen_class)

        assert screen_class.PANELS, f"{screen_class.__name__} declares no PANELS"

        seen: list[type] = []
        for widget_class, adapt in screen_class.PANELS:
            where = f"{screen_class.__name__} -> {widget_class.__name__}"
            assert widget_class not in seen, f"{where}: named twice in PANELS"
            seen.append(widget_class)

            # In compose, and exactly once: query_one raises otherwise.
            screen.query_one(widget_class)

            adapted = adapt(payload)
            assert isinstance(adapted, dict), f"{where}: adapter returned {type(adapted)}"

            params = {
                name: p
                for name, p in inspect.signature(widget_class.update_data).parameters.items()
                if name != "self"
            }
            positional_only = [n for n, p in params.items() if p.kind is p.POSITIONAL_ONLY]
            assert not positional_only, (
                f"{where}: {positional_only} cannot be filled by keyword"
            )
            # Every key must be a NAMED parameter. Most panels end their
            # signature with ``**_kwargs`` for payload forward-compatibility,
            # and honouring that here would make this check toothless against
            # the one failure it exists for: ``minted_pcts`` beside
            # ``minted_pct`` would be accepted, silently discarded, and the
            # box would render "unavailable" forever. A catch-all is not a
            # licence for a key the widget cannot read.
            named = {n for n, p in params.items() if p.kind is not p.VAR_KEYWORD}
            unknown = sorted(set(adapted) - named)
            assert not unknown, (
                f"{where}: adapter sends {unknown}, which update_data names no "
                f"parameter for (it accepts {sorted(named)})"
            )
            required = {
                n
                for n, p in params.items()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            }
            missing = sorted(required - set(adapted))
            assert not missing, f"{where}: required parameter(s) {missing} left unfilled"

        unclaimed = _unclaimed_panels(screen, screen_class)
        assert not unclaimed, (
            f"{screen_class.__name__}: mounted but in no PANELS row (a dropped "
            f"row never updates again): {unclaimed}"
        )
