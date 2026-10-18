"""Only the selected body consumes reader snapshots and unchanged ticks stay cheap."""

from copy import deepcopy
from unittest.mock import Mock

from textual.app import App

from maxpane_dashboard.screens.surf import SurfScreen, SURF_MODES
from maxpane_dashboard.widgets.status_bar import StatusBar
from tests.screens.test_surf_screen import _FakeManager, _Harness, _frozen_payload


def painted(screen):
    return '\n'.join(strip.text for strip in screen._compositor.render_strips())


async def test_refresh_dispatches_only_the_selected_body(monkeypatch):
    screen = SurfScreen(_FakeManager(_frozen_payload()))
    app = _Harness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen._refresh_timer.pause()
        calls = {}
        widgets = [widget for widget in screen.walk_children()
                   if type(widget).__name__.startswith('Surf') and hasattr(widget, 'update_data')]
        for widget in widgets:
            calls[widget] = Mock(wraps=widget.update_data)
            monkeypatch.setattr(widget, 'update_data', calls[widget])
        for mode in SURF_MODES:
            screen._mode = mode
            screen._show_mode(refresh=False)
            screen._stop_oracles_timer()
            screen._stop_launch_contribution_timer()
            for call in calls.values():
                call.reset_mock()
            await screen._do_refresh()
            await pilot.pause()
            hidden_calls = [type(widget).__name__ for widget, call in calls.items()
                            if call.called and not all(node.display for node in (widget, *widget.ancestors))]
            assert not hidden_calls, (mode, hidden_calls)
            missing_calls = [type(widget).__name__ for widget, call in calls.items()
                             if not call.called and all(node.display for node in (widget, *widget.ancestors))]
            assert not missing_calls, (mode, missing_calls)
            assert 'q quit' in painted(screen)


async def test_passive_oracle_ticks_only_repaint_changed_snapshots(monkeypatch):
    from maxpane_dashboard.widgets.surf.oracles import SurfOraclesBody, SurfOraclesHero

    payload = _frozen_payload()
    manager = _FakeManager(payload)
    snapshot = deepcopy(payload.get('surf_oracles') or {'rows': []})
    manager.get_oracles_snapshot = lambda: deepcopy(snapshot)
    screen = SurfScreen(manager)
    screen.open_mode('oracles')
    app = _Harness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen._stop_oracles_timer()
        screen._refresh_timer.pause()
        hero, body = screen.query_one(SurfOraclesHero), screen.query_one(SurfOraclesBody)
        updates = Mock(wraps=body.update_data)
        monkeypatch.setattr(body, 'update_data', updates)
        screen._tick_oracles()
        await pilot.pause()
        before = updates.call_count
        for _ in range(4):
            screen._tick_oracles()
        assert updates.call_count == before
        snapshot['read_ts'] = 1234567
        screen._tick_oracles()
        await pilot.pause()
        assert updates.call_count == before + 1
        assert 'REQUESTS' in painted(screen)


async def test_passive_contribution_ticks_only_repaint_changed_snapshots(monkeypatch):
    from maxpane_dashboard.widgets.surf.swarm_board_hero import SurfSwarmBoardHero

    manager = _FakeManager(_frozen_payload())
    snapshot = {'summary': {'launches': 7}}
    manager.offer_launch_contribution = Mock()
    manager.get_launch_contribution_snapshot = lambda: deepcopy(snapshot)
    screen = SurfScreen(manager)
    screen.open_mode('board')
    app = _Harness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen._stop_launch_contribution_timer()
        screen._refresh_timer.pause()
        hero = screen.query_one(SurfSwarmBoardHero)
        updates = Mock(wraps=hero.set_launch_contribution)
        monkeypatch.setattr(hero, 'set_launch_contribution', updates)
        screen._tick_launch_contribution()
        before = updates.call_count
        for _ in range(4):
            screen._tick_launch_contribution()
        assert updates.call_count == before
        snapshot['summary']['launches'] = 8
        screen._tick_launch_contribution()
        await pilot.pause()
        assert updates.call_count == before + 1
        assert 'LAUNCHES' in painted(screen)


async def test_repeated_loading_state_does_not_repaint_but_animation_continues(monkeypatch):
    class FooterApp(App):
        def compose(self):
            yield StatusBar()

    app = FooterApp()
    async with app.run_test(size=(149, 45)) as pilot:
        bar = app.query_one(StatusBar)
        bar.set_loading(True)
        bar._loading_timer.pause()
        updates = Mock(wraps=bar._update_message)
        monkeypatch.setattr(bar, '_update_message', updates)
        for _ in range(4):
            bar.set_loading(True)
        assert not updates.called
        bar._tick_loading()
        await pilot.pause()
        assert '◓ loading' in painted(app.screen)
        bar.set_loading(False)
        await pilot.pause()
        assert 'loading' not in painted(app.screen)


async def test_boardroom_loading_tick_skips_unchanged_local_snapshot(monkeypatch):
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from maxpane_dashboard.widgets.surfboard import SurfboardRack
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import HubPayloadManager, hub_payload

    snapshot = hub_payload()
    work = next(card for card in snapshot['surfboard_cards'] if card['key'] == 'work')
    work['status'] = 'loading'
    manager = HubPayloadManager(deepcopy(snapshot))
    manager.get_hub_snapshot = lambda: deepcopy(snapshot)
    app = HubHarness(snapshot)
    app.hub = SurfboardScreen(manager)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen = app.hub
        screen._age_timer.pause()
        screen._refresh_timer.pause()
        rack = screen.query_one(SurfboardRack)
        updates = Mock(wraps=rack.update_data)
        monkeypatch.setattr(rack, 'update_data', updates)
        for _ in range(4):
            screen._tick_terminal_age()
        await app.workers.wait_for_complete()
        assert not updates.called
        work['status'] = 'ok'
        screen._tick_terminal_age()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert updates.call_count == 1
        assert '◌ loading' not in painted(screen)
