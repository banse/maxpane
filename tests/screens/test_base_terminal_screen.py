"""Headless Textual tests for the Base Terminal screen.

Covers LOW-17: on a failed refresh the screen used to hardcode
``error_count=0`` into the StatusBar even though ``BaseManager`` had just
incremented ``_error_count``, so the status bar claimed "no errors" during
an active outage.  Every sibling screen passes the manager's real count.

No network: the fake manager either returns a small data dict or raises.
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Static

from maxpane_dashboard.screens.base_terminal import BaseTerminalScreen
from maxpane_dashboard.widgets.status_bar import StatusBar


class _FakeManager:
    """Stand-in for BaseManager that never touches the network."""

    def __init__(self, *, fail: bool = False, error_count: int = 0) -> None:
        self._error_count = error_count
        self.fail = fail
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self.fail:
            # Mirror BaseManager.fetch_and_compute: count, then re-raise.
            self._error_count += 1
            raise RuntimeError("network down")
        return {
            "eth_price": "$3,000",
            "gas_price": "0.01 gwei",
            "trending_tokens": [],
            "last_updated_seconds_ago": 0,
            "error_count": self._error_count,
            "poll_interval": 30,
        }

    async def close(self) -> None:
        pass


class _Harness(App):
    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _status_text(screen: BaseTerminalScreen) -> str:
    widget = screen.query_one(StatusBar).query_one("#status-left", Static)
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


@pytest.mark.asyncio
async def test_screen_mounts_and_refreshes() -> None:
    manager = _FakeManager()
    screen = BaseTerminalScreen(manager, poll_interval=30, name="base")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1
        assert "errors" not in _status_text(screen)


@pytest.mark.asyncio
async def test_failed_refresh_reports_the_managers_error_count() -> None:
    """LOW-17: the error indicator must survive the failure that caused it."""
    manager = _FakeManager(fail=True, error_count=2)
    screen = BaseTerminalScreen(manager, poll_interval=30, name="base")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()  # must not raise
        await pilot.pause()

        # The screen also refreshes on resume, so only the relationship
        # between the two matters: whatever the manager counted is what the
        # status bar shows.  Before the fix this was always "0 errors".
        assert manager._error_count >= 3
        text = _status_text(screen)
        assert f"{manager._error_count} errors" in text, text


@pytest.mark.asyncio
async def test_failed_refresh_tolerates_a_manager_without_error_count() -> None:
    """Degrade like the sibling screens rather than crash the error path."""

    class _Bare:
        async def fetch_and_compute(self) -> dict:
            raise RuntimeError("boom")

    screen = BaseTerminalScreen(_Bare(), poll_interval=30, name="base")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()  # must not raise
        await pilot.pause()
        assert "errors" not in _status_text(screen)
