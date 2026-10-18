"""Measured layout boundaries against the real, bundled documentation."""
from pathlib import Path

import pytest
from textual.containers import VerticalScroll

from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager
from maxpane_dashboard.screens.workflow_guide import (
    WorkflowGuideScreen, WORKFLOW_GUIDE_FULL_LAYOUT_COLUMNS as WIDTH,
    WORKFLOW_GUIDE_FULL_LAYOUT_ROWS as HEIGHT,
)
from maxpane_dashboard.widgets.workflow_guide import WorkflowGuideView
from tests.screens._sweeps import boundary_set
from tests.screens.test_workflow_guide import Harness, painted, target


@pytest.mark.guard
def test_screen_rules_match_production_stylesheet():
    css = (Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss').read_text()
    block = css.split('/* WORKFLOW GUIDE */')[1].split('/* END WORKFLOW GUIDE */')[0]
    assert block.strip() == WorkflowGuideScreen.DEFAULT_CSS.strip()


@pytest.mark.parametrize('production_css', [False, True])
async def test_every_bundled_diagram_is_whole_with_index_open_and_closed(production_css):
    app = Harness(manager=WorkflowGuideManager())
    if not production_css:
        app.css_path = []
    async with app.run_test(size=(WIDTH, HEIGHT)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        for index_open in (False, True):
            if index_open:
                view.toggle_index()
            for i, topic in enumerate(view.topics):
                view.select_topic(i)
                await pilot.pause()
                viewport = app.screen.query_one('#workflow-viewport', VerticalScroll)
                diagram = app.screen.query_one('#workflow-diagram-scroll', VerticalScroll)
                assert viewport.max_scroll_x == viewport.max_scroll_y == 0
                assert diagram.max_scroll_x == diagram.max_scroll_y == 0
                output = painted(app)
                for title in ('EXPLANATION', 'LIMITS', 'DOCUMENTED EXAMPLE'):
                    assert title in output
                for n, node in enumerate(topic['nodes']):
                    assert node['label'] in output
                    target(app, f'choose_node({n})')


@pytest.mark.sweep
@pytest.mark.parametrize('width', boundary_set(WIDTH, 130, 160))
async def test_width_pin_matches_actual_outer_overflow_and_hint(width):
    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(0)  # Widest authored diagram.
        view.toggle_index()
        await pilot.pause()
        viewport = app.screen.query_one('#workflow-viewport', VerticalScroll)
        assert (viewport.max_scroll_x > 0) == (width < WIDTH)
        assert ('‹ widen' in painted(app)) == (width < WIDTH)


@pytest.mark.sweep
@pytest.mark.parametrize('height', boundary_set(HEIGHT, 35, 50))
async def test_height_pin_matches_tallest_diagram_and_hint(height):
    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, height)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(2)  # STEP SHAPES is the source's tallest diagram.
        await pilot.pause()
        viewport = app.screen.query_one('#workflow-viewport', VerticalScroll)
        assert (viewport.max_scroll_y > 0) == (height < HEIGHT)
        assert ('‹ taller' in painted(app)) == (height < HEIGHT)
