"""Boardroom entry and retained guide state; all managers are local."""
from textual.widgets import Input

from tests.screens.test_surfboard_screen import hub_app, painted


async def test_boardroom_workflows_entry_retains_title_and_does_not_steal_input():
    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        heading = hub.query_one('#surfboard-title')
        title = painted(app).splitlines()[heading.region.y][heading.region.x:heading.region.right]
        assert title.index('IMD BOARDROOM') == (heading.region.width - len('IMD BOARDROOM')) // 2
        assert 'WORKFLOWS [g]' in title
        await pilot.press('/')
        assert isinstance(hub.focused, Input)
        await pilot.press('g')
        assert app.screen is hub and hub.focused.value == 'g'


async def test_guide_route_stops_hub_reads_and_reopens_retained_selection():
    from maxpane_dashboard.screens.workflow_guide import WorkflowGuideScreen
    from maxpane_dashboard.widgets.workflow_guide import WorkflowGuideView

    app, _ = hub_app()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        manager = hub._data_manager
        await pilot.press('g')
        assert isinstance(app.screen, WorkflowGuideScreen)
        guide = app.screen
        assert not manager.hub_active and hub._refresh_timer is None
        assert guide._refresh_timer is None
        await pilot.press('right', 'down', 'i')
        view = guide.query_one(WorkflowGuideView)
        selection = view.topic_id, view.node_id, view.index_open
        await pilot.press('escape')
        assert app.screen is hub and manager.hub_active
        heading = hub.query_one('#surfboard-title')
        title = painted(app).splitlines()[heading.region.y][heading.region.x:heading.region.right]
        await pilot.click('#surfboard-title', offset=(title.index('WORKFLOWS'), 0))
        assert isinstance(app.screen, WorkflowGuideScreen)
        assert app.screen._data_manager is guide._data_manager
        view = app.screen.query_one(WorkflowGuideView)
        assert (view.topic_id, view.node_id, view.index_open) == selection
