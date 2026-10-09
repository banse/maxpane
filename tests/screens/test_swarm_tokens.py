"""Offline interaction and composited layout of the approved market overview."""
import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Select

from maxpane_dashboard.demos.swarm_tokens import SwarmTokensDemo
from maxpane_dashboard.screens.swarm_tokens import (
    SwarmTokensScreen, SWARM_TOKENS_FULL_LAYOUT_COLUMNS, SWARM_TOKENS_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.widgets.swarm_tokens import TokensTable


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.mark.guard
def test_screen_css_agrees_with_application_stylesheet():
    from pathlib import Path
    css=(Path(__file__).resolve().parents[2]/'maxpane_dashboard/themes/minimal.tcss').read_text()
    block=css.split('/* SWARM TOKENS mock screen */',1)[-1]
    assert ' '.join(block.split())==' '.join(SwarmTokensScreen.DEFAULT_CSS.split())


@pytest.mark.sweep
@pytest.mark.parametrize('axis,delta',[('width',-1),('width',0),('width',1),
                                     ('height',-1),('height',0),('height',1)])
async def test_measured_layout_boundary_matches_composited_content(axis,delta):
    width=SWARM_TOKENS_FULL_LAYOUT_COLUMNS+(delta if axis=='width' else 0)
    height=SWARM_TOKENS_FULL_LAYOUT_ROWS+(delta if axis=='height' else 0)
    app=SwarmTokensDemo()
    async with app.run_test(size=(width,height)) as pilot:
        await pilot.pause()
        viewport=app.screen.query_one('#st-viewport',VerticalScroll)
        text=painted(app)
        cut=viewport.show_horizontal_scrollbar or viewport.show_vertical_scrollbar
        assert cut == (delta<0)
        assert ('‹ widen' in text)==viewport.show_horizontal_scrollbar
        assert ('‹ taller' in text)==viewport.show_vertical_scrollbar
        table=app.screen.query_one(DataTable)
        assert table.row_count==24
        assert not table.show_horizontal_scrollbar
        if not cut:
            for label in ('NEWLY LAUNCHED','BEST PLAYS','ACTIVITY','PAIRED LP',
                          'PRICE 24H','LP STATE','VERDICT'):
                assert label in text
            assert app.screen.query_one('#st-bottom').region.bottom <= viewport.region.bottom


async def test_small_terminal_advertises_scroll_and_retains_full_table():
    app=SwarmTokensDemo()
    async with app.run_test(size=(100,28)) as pilot:
        await pilot.pause()
        assert '‹ widen' in painted(app) and '‹ taller' in painted(app)
        viewport=app.screen.query_one('#st-viewport',VerticalScroll)
        viewport.scroll_to(x=viewport.max_scroll_x,y=viewport.max_scroll_y,animate=False)
        await pilot.pause()
        assert 'ACTIVITY' in painted(app)
        assert app.screen.query_one(DataTable).row_count==24


async def test_mock_overview_renders_all_panels_and_every_token_without_network():
    app = SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        text = painted(app)
        for word in ('MOCK DATA','SWARM TOKENS','NEWLY LAUNCHED','BEST PLAYS','ACTIVITY','PAIRED','LP STATE'):
            assert word in text
        assert app.screen.query_one(TokensTable).query_one(DataTable).row_count == 24
        assert 'one-token' in text and 'two-sided' in text
        assert any(char in text for char in '▂▃▄▅▆▇█')


async def test_filters_apply_across_panels_and_search_can_return_no_matches():
    app = SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one('#st-chain',Select).value = 'base'
        await pilot.pause()
        assert screen.snapshot['tokens']
        assert all(row['chain']=='base' for row in screen.snapshot['tokens'])
        assert all(row['chain']=='base' for row in screen.snapshot['newly_launched'])
        ids={row['id'] for row in screen.snapshot['tokens']}
        assert all(event['token_id'] in ids for event in screen.snapshot['activity'])
        assert screen.snapshot['metrics']['total']==len(ids)
        screen.query_one('#st-search',Input).value='no such token'
        await pilot.pause()
        assert screen.snapshot['tokens']==[]
        assert screen.snapshot['activity']==[]
        assert 'No matching tokens' in painted(app)
        screen.query_one('#st-search',Input).value=''
        screen.query_one('#st-lp',Select).value='one-sided'
        await pilot.pause()
        assert all(row['lp_state'] in ('one-token','one-quote') for row in screen.snapshot['tokens'])


async def test_selected_token_survives_sort_refresh_and_opens_mock_details():
    app = SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        panel=app.screen.query_one(TokensTable)
        table=panel.query_one(DataTable)
        table.focus()
        table.move_cursor(row=2)
        await pilot.pause()
        selected=panel.selected_token()['id']
        app.screen.query_one('#st-sort',Select).value='newest'
        await pilot.pause()
        assert panel.selected_token()['id']==selected
        app.screen.action_refresh()
        await pilot.pause()
        assert panel.selected_token()['id']==selected
        table.focus()
        await pilot.press('enter')
        await pilot.pause()
        assert 'MOCK DATA' in painted(app) and 'LAUNCH POSITION' in painted(app)
        await pilot.press('escape')
        assert isinstance(app.screen,SwarmTokensScreen)


async def test_hub_demo_route_returns_with_terminal_draft_and_card_focus():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.widgets.surfboard.rack import SurfboardRack
    app,managers=hub_app()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        hub=app.screen
        command=hub.query_one(Input)
        command.value='status'
        rack=hub.query_one(SurfboardRack)
        rack.focus_card('swarm-tokens')
        await pilot.press('enter')
        await pilot.pause()
        assert isinstance(app.screen,SwarmTokensScreen)
        assert not managers['_surf_manager'].hub_active
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen is hub
        assert command.value=='status'
        assert rack.focused_card=='swarm-tokens'
        assert managers['_surf_manager'].hub_active
