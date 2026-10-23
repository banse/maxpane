"""The shared footer reports active work without moving its visual centre."""

from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.status_bar import StatusBar


class FooterApp(App):
    CSS_PATH = Path(__file__).parents[2] / "maxpane_dashboard/themes/minimal.tcss"

    def compose(self):
        yield StatusBar()

    def on_mount(self):
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"


class ManualTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.stopped = False

    def stop(self):
        self.stopped = True


@pytest.fixture
def timers(monkeypatch):
    created = []

    def interval(_widget, seconds, callback, **kwargs):
        timer = ManualTimer(seconds, callback)
        created.append(timer)
        return timer

    monkeypatch.setattr(StatusBar, "set_interval", interval)
    return created


def footer(app):
    return app.screen._compositor.render_strips()[-1].text


@pytest.mark.parametrize("width", [149, 63, 64])
async def test_loading_is_centred_across_the_full_footer(width, timers):
    app = FooterApp()
    async with app.run_test(size=(width, 45)) as pilot:
        bar = app.query_one(StatusBar)
        bar.set_game_name("NFT EXPLORER WITH UNEQUAL FOOTER SIDES")
        bar.set_loading(True)
        await pilot.pause()
        row = footer(app)
        assert "◐ loading" in row
        assert abs(row.index("◐ loading") + 4 - (width - 1) / 2) <= 0.5, row
        assert len(row) == width


async def test_loading_ticks_and_stops_without_a_late_callback_reviving_it(timers):
    app = FooterApp()
    async with app.run_test(size=(149, 45)) as pilot:
        bar = app.query_one(StatusBar)
        bar.set_loading(True)
        bar.set_loading(True)
        assert len(timers) == 1
        assert timers[0].interval == 0.2
        for frame in "◐◓◑◒◐":
            await pilot.pause()
            assert f"{frame} loading" in footer(app)
            timers[0].callback()
        bar.set_loading(False)
        timers[0].callback()
        await pilot.pause()
        assert timers[0].stopped
        assert "loading" not in footer(app)
        bar.set_loading(True)
        await pilot.pause()
        assert len(timers) == 2
        assert "◐ loading" in footer(app)
        await bar.remove()
        timers[-1].callback()
        await pilot.pause()
        assert timers[-1].stopped
        assert "loading" not in footer(app)


async def test_footer_omits_refresh_hints_poll_age_and_source_errors(timers):
    app = FooterApp()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "connecting" not in footer(app)
        bar = app.query_one(StatusBar)
        bar.set_key_hints("p protocol · w work · / cmd · esc")
        bar.update_data(last_updated_seconds_ago=9999, error_count=7, poll_interval=30)
        await pilot.pause()
        row = footer(app)
        assert "q quit · m menu · tab switch" in row
        for removed in ("r refresh", "p protocol", "w work", "/ cmd", "esc",
                        "poll", "updated", "errors", "stale", "unavailable"):
            assert removed not in row, row


async def test_operation_message_is_literal_and_returns_after_loading(timers):
    app = FooterApp()
    async with app.run_test(size=(149, 45)) as pilot:
        bar = app.query_one(StatusBar)
        bar.set_message("copied [/x] \x1b[red]")
        await pilot.pause()
        assert "copied [/x] [red]" in footer(app)
        bar.set_loading(True)
        bar.set_message("answer no longer listed")
        await pilot.pause()
        assert "loading" in footer(app)
        assert "answer no longer listed" not in footer(app)
        bar.set_loading(False)
        await pilot.pause()
        assert "answer no longer listed" in footer(app)
        assert bar.message == "answer no longer listed"
        bar.set_message("")
        await pilot.pause()
        assert "answer no longer listed" not in footer(app)


async def test_loading_and_message_can_be_set_before_mount(timers):
    bar = StatusBar()
    bar.set_game_name("BOARDROOM")
    bar.set_message("copied selection")
    bar.set_loading(True)
    assert not timers

    class PrimedFooter(FooterApp):
        def compose(self):
            yield bar

    app = PrimedFooter()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "◐ loading" in footer(app)
        assert "BOARDROOM" in footer(app)
        assert len(timers) == 1
        bar.set_loading(False)
        await pilot.pause()
        assert "copied selection" in footer(app)


async def test_external_frames_replace_private_timer_and_ignore_late_ticks(timers):
    app = FooterApp()
    async with app.run_test(size=(149, 45)) as pilot:
        bar = app.query_one(StatusBar)
        bar.set_loading(True)
        old_timer = timers[0]
        for phase in (0, 3, 4, 7, 1):
            bar.set_loading(True, frame=phase)
            old_timer.callback()
            await pilot.pause()
            assert f"{'◐◓◑◒'[phase % 4]} loading" in footer(app)
            assert old_timer.stopped and bar._loading_timer is None
            assert len(timers) == 1
        bar.set_loading(False, frame=0)
        old_timer.callback()
        await pilot.pause()
        assert 'loading' not in footer(app)
        bar.set_loading(True)
        await pilot.pause()
        assert len(timers) == 2 and '◐ loading' in footer(app)


async def test_external_phase_survives_mount_without_starting_a_timer(timers):
    bar = StatusBar()
    bar.set_loading(True, frame=7)

    class PrimedFooter(FooterApp):
        def compose(self):
            yield bar

    app = PrimedFooter()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert '◒ loading' in footer(app)
        assert not timers


@pytest.mark.parametrize("kind,game,is_mock,hints", [
    ("overview", "SWARM TOKENS", False, ""),
    ("overview", "SWARM TOKENS · MOCK DATA", True, ""),
    ("overview", "PORTFOLIO", False, "r refresh · esc back · f filter"),
    ("detail", "SWARM TOKEN", False, "r refresh · esc back"),
])
async def test_token_and_portfolio_footers_use_shared_loading_navigation(
    kind, game, is_mock, hints, timers,
):
    from maxpane_dashboard.screens.swarm_tokens import DemoStatusBar
    from maxpane_dashboard.screens.swarm_token_detail import TokenStatusBar

    bar = TokenStatusBar() if kind == "detail" else DemoStatusBar()
    bar.is_mock = is_mock
    bar.set_game_name(game)
    bar.set_key_hints(hints)

    class TokenFooter(FooterApp):
        def compose(self):
            yield bar

    app = TokenFooter()
    async with app.run_test(size=(149, 45)) as pilot:
        bar.update_data(999, 4, 30)
        bar.set_loading(True)
        await pilot.pause()
        row = footer(app)
        assert "q quit · m menu · tab switch" in row
        assert row.index("◐ loading") + 4 == 74
        assert game in row
        for removed in ("r refresh", "esc back", "f filter", "poll", "30s", "errors"):
            assert removed not in row, row
