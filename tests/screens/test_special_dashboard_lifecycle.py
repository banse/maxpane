"""Custom dispatchers still use the shared cached-entry and refresh boundary."""

import asyncio
import copy
from pathlib import Path

import pytest
from textual.app import App
from textual.screen import Screen


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / "maxpane_dashboard/themes/minimal.tcss"

    def __init__(self, screen):
        super().__init__()
        self.board = screen

    def on_mount(self):
        self.push_screen(self.board)


def example(kind):
    if kind == "fwa":
        from maxpane_dashboard.screens.fwa import FWAScreen
        from tests.screens.test_fwa_screen import _FakeManager, _frozen_payload
        cached = _frozen_payload(active_positions=3867)
        fresh = dict(cached, active_positions=4567)
        screen = FWAScreen(_FakeManager(cached))
        return screen, cached, fresh, "3,867 positions", "4,567 positions"
    if kind == "curator":
        from tests.screens.test_curator_screen import _grace_payload, _screen
        cached = _grace_payload()
        fresh = dict(cached, current_hour=5)
        return _screen(cached), cached, fresh, "THE LIST · hour 4", "THE LIST · hour 5"
    from maxpane_dashboard.screens.frenpet_full import FrenPetFullScreen
    from tests.screens.test_frenpet_screens import _FakeManager, _sample_data
    cached = _sample_data()
    cached["population_stats"]["total"] = 12345
    fresh = copy.deepcopy(cached)
    fresh["population_stats"]["total"] = 23456
    return FrenPetFullScreen(_FakeManager()), cached, fresh, "12,345", "23,456"


def painted(screen):
    return "\n".join(strip.text for strip in screen._compositor.render_strips())


@pytest.mark.parametrize("kind", ["fwa", "curator", "frenpet_full"])
async def test_custom_dispatcher_paints_cache_before_first_read_and_reopen(kind):
    screen, cached, fresh, cached_marker, fresh_marker = example(kind)
    snapshot = copy.deepcopy(cached)
    started = asyncio.Queue()
    release = asyncio.Event()
    reads = 0

    async def fetch():
        nonlocal reads, snapshot
        reads += 1
        started.put_nowait(reads)
        await release.wait()
        snapshot = copy.deepcopy(fresh)
        return copy.deepcopy(snapshot)

    screen._data_manager.get_snapshot = lambda: copy.deepcopy(snapshot)
    screen._data_manager.fetch_and_compute = fetch
    app = Harness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        assert await asyncio.wait_for(started.get(), 2) == 1
        await pilot.pause()
        assert cached_marker in painted(screen)
        assert fresh_marker not in painted(screen)
        assert "loading" in painted(screen).splitlines()[-1]
        release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert fresh_marker in painted(screen)
        assert reads == 1

        await app.push_screen(Screen())
        release.clear()
        app.pop_screen()
        assert await asyncio.wait_for(started.get(), 2) == 2
        await pilot.pause()
        assert fresh_marker in painted(screen)
        assert "loading" in painted(screen).splitlines()[-1]
        release.set()
        await app.workers.wait_for_complete()
        assert reads == 2
