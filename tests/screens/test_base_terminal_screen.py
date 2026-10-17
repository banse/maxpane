"""Headless Textual tests for the Base Terminal screen.

A failed refresh keeps the screen standing and the footer compact.
Error accounting remains in the manager, without source-health footer labels.

No network: the fake manager either returns a small data dict or raises.
"""

from __future__ import annotations

import pytest
from textual.app import App

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
    bar = screen.query_one(StatusBar)
    return screen._compositor.render_strips()[bar.region.y].text


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
async def test_failed_refresh_retains_internal_errors_without_footer_warnings() -> None:
    """The source failure is counted without replacing navigation or cached panels."""
    manager = _FakeManager(fail=True, error_count=2)
    screen = BaseTerminalScreen(manager, poll_interval=30, name="base")
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await screen._do_refresh()  # must not raise
        await pilot.pause()

        assert manager._error_count >= 3
        text = _status_text(screen)
        assert "q quit · m menu · tab switch" in text
        assert "errors" not in text
        assert "updated" not in text


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
