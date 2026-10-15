"""Real Surf refresh/routing and native Textual toasts, with local managers only."""
from copy import deepcopy

import pytest
from textual.screen import Screen
from textual.widgets._toast import Toast

from maxpane_dashboard.launch_notifications import SurfLaunchesUpdated
from maxpane_dashboard.screens.surf import (
    MODE_AGENT, MODE_BOARD, MODE_DASHBOARD, MODE_LAUNCHPAD, MODE_ORACLES,
    MODE_POOL4, MODE_POOL4_USER, MODE_SWARM, MODE_WORK,
)
from tests.screens.test_surfboard_screen import HubManager, hub_app, painted
from tests.test_launch_notifications import fired, snapshot, tracker


class LaunchManager(HubManager):
    def __init__(self):
        super().__init__()
        self.data = snapshot(state="ok")

    async def fetch_and_compute(self):
        return deepcopy(self.data)

    async def fetch_hub_snapshot(self):
        return {**await super().fetch_hub_snapshot(), **deepcopy(self.data)}


def launch_app():
    app, _ = hub_app()
    manager = LaunchManager()
    app._surf_manager = manager
    app._launch_notifications, clock = tracker()
    return app, manager, clock


@pytest.mark.parametrize("mode", [None, MODE_DASHBOARD, MODE_LAUNCHPAD, MODE_POOL4,
    MODE_POOL4_USER, MODE_SWARM, MODE_AGENT, MODE_BOARD, MODE_ORACLES, MODE_WORK])
async def test_toast_is_painted_in_boardroom_and_every_surf_mode(mode):
    app, manager, clock = launch_app()
    async with app.run_test(size=(149, 45), notifications=True) as pilot:
        await pilot.pause()
        if mode is not None:
            app.open_surf_mode(mode)
            await pilot.pause()
        assert not app.screen.query(Toast)
        clock.now = 1002.
        manager.data = snapshot([dict(fired(), ticker="[red]X\nY")])
        await app.screen._do_refresh()
        await pilot.pause()
        assert len(app.screen.query(Toast)) == 1
        assert "Token launched" in painted(app)
        assert "$[red]X Y · MAINNET" in painted(app)
        assert "Launch #737" in painted(app)
        toast = app.screen.query_one(Toast)
        assert toast._notification.timeout == 10
        await app.screen._do_refresh()
        await pilot.pause()
        assert len(app._notifications) == 1


async def test_view_switches_and_hidden_refreshes_share_one_notification_history():
    app, manager, clock = launch_app()
    async with app.run_test(size=(149, 45), notifications=True) as pilot:
        await pilot.pause()
        hub = app.screen
        clock.now = 1002.
        manager.data = snapshot([fired(), fired(747)])
        await app.push_screen(Screen())
        hub.post_message(SurfLaunchesUpdated(hub, deepcopy(manager.data)))
        await pilot.pause()
        assert len(app._notifications) == 0
        await app.pop_screen()
        await pilot.pause()
        assert len(app._notifications) == 2
        app.open_surf_mode(MODE_BOARD)
        await pilot.pause()
        assert len(app._notifications) == 2
        app.return_to_surfboard()
        await pilot.pause()
        assert len(app._notifications) == 2
