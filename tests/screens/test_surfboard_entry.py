"""Actual terminal reveal and navigation, with clocks and local data only."""
from textual.screen import Screen

from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import hub_payload


def terminal_rows(app):
    region = app.hub.query_one(SurfboardTerminal).region
    return [row.crop(region.x, region.right) for row in
            app.hub._compositor.render_strips()[region.y:region.bottom]]


async def test_entry_covers_whole_terminal_and_reveals_latest_data_without_moving_cards():
    app = HubHarness(hub_payload())
    now = [0.0]
    app.hub._age_clock = lambda: now[0]
    app.hub.prepare_entry_animation()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        overlay = app.hub._terminal_reveal
        terminal = app.hub.query_one(SurfboardTerminal)
        assert overlay.display and overlay.region == terminal.region
        assert (terminal.region.y, terminal.region.height) == (12, 31)
        assert all('╭' not in row.text and '╰' not in row.text for row in terminal_rows(app))
        assert '? for commands' not in '\n'.join(row.text for row in terminal_rows(app))
        assert 'FLEET' in '\n'.join(row.text for row in app.hub._compositor.render_strips())
        terminal.add_reply('LATEST LIVE UPDATE')
        now[0] = 4.2
        app.hub._tick_entry_animation()
        await pilot.pause()
        assert 'LATEST LIVE UPDATE' in '\n'.join(row.text for row in terminal_rows(app))
        terminal.add_reply('SECOND LIVE UPDATE')
        await pilot.pause()  # the real terminal restores its transcript scroll after refresh
        now[0] = 4.3
        app.hub._tick_entry_animation()
        await pilot.pause()
        assert 'SECOND LIVE UPDATE' in '\n'.join(row.text for row in terminal_rows(app))
        now[0] = 5.1
        app.hub._tick_entry_animation()
        await pilot.pause()
        assert not overlay.display and app.hub._entry_timer is None
        assert '? for commands' in '\n'.join(row.text for row in terminal_rows(app))
        assert (terminal.region.y, terminal.region.height) == (12, 31)


async def test_suspend_cancels_reveal_and_resume_never_replays_it():
    app = HubHarness(hub_payload())
    app.hub.prepare_entry_animation()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert app.hub._entry_timer is not None
        await app.push_screen(Screen())
        await pilot.pause()
        assert app.hub._entry_timer is None and not app.hub._terminal_reveal.display
        await app.pop_screen()
        await pilot.pause()
        assert app.hub._entry_timer is None


async def test_resize_and_scroll_keep_overlay_on_terminal_and_command_input_reveals():
    app = HubHarness(hub_payload())
    app.hub._age_clock = lambda: 0
    app.hub.prepare_entry_animation()
    async with app.run_test(size=(149, 45)) as pilot:
        for size in ((143, 37), (110, 30), (149, 45)):
            await pilot.resize_terminal(*size)
            await pilot.pause()
            app.hub._tick_entry_animation()
            await pilot.pause()
            terminal = app.hub.query_one(SurfboardTerminal)
            viewport = app.hub.query_one('#surfboard-viewport')
            assert app.hub._terminal_reveal.region == terminal.region.intersection(viewport.content_region)
        await pilot.press('slash', 'h', 'i')
        assert app.hub._entry_timer is None
        assert not app.hub._terminal_reveal.display
        assert terminal.command_input.value == 'hi'


async def test_explicit_entry_replays_but_switched_subview_return_does_not():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.screens.surf import MODE_WORK
    app, managers = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        hub._age_clock = lambda: 0
        assert hub._entry_timer is not None
        assert managers['_surf_manager'].hub_reads > 0  # fetch during animation
        app.open_surf_mode(MODE_WORK)
        await pilot.pause()
        assert hub._entry_timer is None
        app.return_to_surfboard()
        await pilot.pause()
        assert app.screen is hub and hub._entry_timer is None
        await pilot.press('m', '9')
        await pilot.pause()
        assert app.screen is hub and hub._entry_timer is not None
        await pilot.press('tab')
        await pilot.pause()
        assert hub._entry_timer is None
        app._launch_game('surfboard')
        await pilot.pause()
        assert app.screen is hub and hub._entry_timer is not None


async def test_cancel_before_deferred_entry_does_not_replay():
    app = HubHarness(hub_payload())
    app.hub.prepare_entry_animation()
    app.hub._stop_entry_animation()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert app.hub._entry_timer is None and not app.hub._terminal_reveal.display


async def test_complete_fade_preserves_wide_text_when_horizontally_scrolled():
    app = HubHarness(hub_payload('wide'))
    now = [0.0]
    app.hub._age_clock = lambda: now[0]
    app.hub.prepare_entry_animation()
    async with app.run_test(size=(85, 30)) as pilot:
        await pilot.pause()
        viewport = app.hub.query_one('#surfboard-viewport')
        viewport.scroll_to(x=55, y=10, animate=False, immediate=True)
        now[0] = 4.99
        app.hub._tick_entry_animation()
        await pilot.pause()
        shown = [row.text for row in app.hub._compositor.render_strips()]
        app.hub._stop_entry_animation()
        await pilot.pause()
        actual = [row.text for row in app.hub._compositor.render_strips()]
        assert shown == actual


async def test_click_on_reveal_focuses_live_prompt_without_activating_hidden_links():
    app = HubHarness(hub_payload())
    app.hub._age_clock = lambda: 0
    app.hub.prepare_entry_animation()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.click(app.hub._terminal_reveal, offset=(4, 4))
        await pilot.press('h', 'i')
        assert app.hub._entry_timer is None
        assert app.hub.query_one(SurfboardTerminal).command_input.value == 'hi'
