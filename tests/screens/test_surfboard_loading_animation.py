"""BOARDROOM captions and missing values follow the footer's shared clock."""
from rich.cells import cell_len
from textual.screen import Screen

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import hub_payload
from tests.widgets.test_status_bar_loading import ManualTimer


def caption_ink(screen, text):
    row = next(row for row in screen._compositor.render_strips() if text in row.text)
    x = cell_len(row.text[:row.text.index(text)])
    return next(iter(row.crop(x, x + 2))).style.color.get_truecolor()


async def test_captions_share_footer_phase_and_restore_idle_on_leave(monkeypatch):
    clocks = []
    original = DashboardScreen.set_interval

    def interval(screen, seconds, callback, **kwargs):
        if callback.__name__ == '_tick_loading':
            timer = ManualTimer(seconds, callback)
            clocks.append(timer)
            return timer
        return original(screen, seconds, callback, **kwargs)

    def forbidden_timer(*args, **kwargs):
        raise AssertionError('screen owns the loading clock')

    monkeypatch.setattr(DashboardScreen, 'set_interval', interval)
    monkeypatch.setattr(StatusBar, 'set_interval', forbidden_timer)
    payload = hub_payload()
    wip = next(card for card in payload['surfboard_cards'] if card['key'] == 'work')
    wip['work_summary'] = {'workflows': None}
    app = HubHarness(payload)
    manager = app.hub._data_manager
    reads = 0
    fetch = manager.fetch_hub_snapshot

    async def fetch_snapshot():
        nonlocal reads
        reads += 1
        return await fetch()

    manager.fetch_hub_snapshot = fetch_snapshot
    pending = False
    manager.is_loading = lambda _view: pending
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen = app.hub
        screen._tick_loading()
        await pilot.pause()
        idle = caption_ink(screen, 'キープ')
        assert idle == (9, 155, 43)
        assert len(clocks) == 1
        initial_reads = reads
        pending = True
        expected = [(9, 155, 43), (6, 180, 48), (4, 205, 54), (2, 230, 59),
                    (0, 255, 65), (2, 230, 59), (4, 205, 54), (6, 180, 48)]
        for phase, ink in enumerate(expected):
            clocks[0].callback()
            await pilot.pause()
            assert caption_ink(screen, 'キープ') == ink
            assert caption_ink(screen, 'ビルディング') == ink
            shade = (28, 77, 127, 176, 226, 176, 127, 77)[phase]
            assert caption_ink(screen, '⛋') == (shade, shade, shade)
            rows = screen._compositor.render_strips()
            assert f"{'◐◓◑◒'[phase % 4]} loading" in rows[-1].text
            assert screen.query_one(StatusBar)._loading_timer is None
            if phase == 4:
                assert any('⛋' in row.text for row in rows)
                await pilot.resize_terminal(143, 37)
                await pilot.pause()
                assert caption_ink(screen, 'キープ') == ink
                assert caption_ink(screen, 'ビルディング') == ink
        assert reads == initial_reads
        # A suspended screen resets both captions and drops its shared timer.
        await app.push_screen(Screen())
        assert clocks[0].stopped and screen._loading_timer is None
        assert screen.query_one('#surfboard-keep').styles.color.rgb == idle
        assert screen.query_one('#surfboard-building').styles.color.rgb == idle
        clocks[0].callback()
        assert screen.query_one('#surfboard-keep').styles.color.rgb == idle
        pending = False
        app.pop_screen()
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen._tick_loading()
        await pilot.pause()
        assert caption_ink(screen, 'キープ') == idle
        assert 'loading' not in screen._compositor.render_strips()[-1].text
        assert len(clocks) == 2
        # A theme change resolves fresh endpoints on the same screen clock.
        app.theme = 'minimal'
        await pilot.pause()
        pending = True
        for _ in range(5):
            clocks[1].callback()
        await pilot.pause()
        assert caption_ink(screen, 'キープ') == (136, 170, 204)
        assert caption_ink(screen, 'ビルディング') == (136, 170, 204)
