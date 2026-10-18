"""Measured layout boundaries against the real, bundled documentation."""
from pathlib import Path

import pytest
from textual.containers import VerticalScroll

from maxpane_dashboard.data.workflow_guide_manager import WorkflowGuideManager
from maxpane_dashboard.screens.workflow_guide import (
    WorkflowGuideScreen, WORKFLOW_GUIDE_FULL_LAYOUT_COLUMNS as WIDTH,
    WORKFLOW_GUIDE_FULL_LAYOUT_ROWS as HEIGHT,
    WORKFLOW_GUIDE_DETAILS_ROWS as DETAILS,
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
                assert 'SOURCE DETAILS >>' in output
                for title in ('STEP INPUT', 'RENDERED', 'MORE ROOM', 'INTEGRATED', 'COST'):
                    assert title in output
                if view.query_one('#workflow-details').display:
                    for title in ('EXPLANATION', 'LIMITS', 'DOCUMENTED EXAMPLE'):
                        assert title in output
                for n, node in enumerate(topic['nodes']):
                    x, y = target(app, f'choose_node({n})')
                    _, _, w, h = view._diagram_boxes[node['id']]
                    rows = output.splitlines()
                    assert rows[y][x] == '┌' and rows[y][x + w - 1] == '┐'
                    assert rows[y + h - 1][x] == '└' and rows[y + h - 1][x + w - 1] == '┘'
                    # Compare all label cells, allowing the source's wrapper
                    # brackets and whitespace to become native card framing.
                    label = node['label'].strip('[]')
                    if node['kind'] == 'plane':
                        label = label.removeprefix('- ').removesuffix(' -')
                    body = ''.join(rows[y + dy][x + 1:x + w - 1] for dy in (1, 2))
                    assert ''.join(label.split()) == ''.join(body.split())


@pytest.mark.sweep
@pytest.mark.parametrize('width', boundary_set(WIDTH, 130, 160))
async def test_width_pin_matches_actual_outer_overflow_and_hint(width):
    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        view.select_topic(3)  # Five-column framed contracts graph.
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
        view.select_topic(3)  # Six stacked parallel stages set the 24-row graph.
        await pilot.pause()
        viewport = app.screen.query_one('#workflow-viewport', VerticalScroll)
        diagram = view.query_one('#workflow-diagram-scroll', VerticalScroll)
        assert (viewport.max_scroll_y > 0 or diagram.max_scroll_y > 0) == (height < HEIGHT)
        assert ('‹ taller' in painted(app)) == (height < HEIGHT)


@pytest.mark.sweep
@pytest.mark.parametrize('height', boundary_set(DETAILS, 45, 60))
async def test_lower_panels_return_only_when_the_complete_diagram_also_fits(height):
    app = Harness(manager=WorkflowGuideManager())
    async with app.run_test(size=(149, height)) as pilot:
        await pilot.pause()
        view = app.screen.query_one(WorkflowGuideView)
        for opened in (False, True):
            if opened:
                view.toggle_index()
            await pilot.pause()
            assert view.query_one('#workflow-details').display == (height >= DETAILS)
            assert ('EXPLANATION' in painted(app)) == (height >= DETAILS)
            assert view.query_one('#workflow-diagram-scroll').max_scroll_y == 0
            target(app, 'open_source')
