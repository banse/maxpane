"""Offline interaction and composited layout of the approved market overview."""
import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Select

from maxpane_dashboard.demos.swarm_tokens import SwarmTokensDemo
from maxpane_dashboard.screens.swarm_tokens import (
    SwarmTokensScreen, SWARM_TOKENS_FULL_LAYOUT_COLUMNS, SWARM_TOKENS_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.widgets.swarm_tokens import (
    TokensTable, TokensHero, NewlyLaunched, BestPlays, TopTraded,
)


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.mark.guard
def test_screen_css_agrees_with_application_stylesheet():
    from pathlib import Path
    css=(Path(__file__).resolve().parents[2]/'maxpane_dashboard/themes/minimal.tcss').read_text()
    block=css.split('/* SWARM TOKENS mock screen */',1)[-1].split('/* SWORN Explorer */',1)[0]
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
        cut=viewport.max_scroll_x > 0 or viewport.max_scroll_y > 0
        assert cut == (delta<0)
        assert ('‹ widen' in text)==(viewport.max_scroll_x > 0)
        assert ('‹ taller' in text)==(viewport.max_scroll_y > 0)
        table=app.screen.query_one(DataTable)
        assert table.row_count==24
        assert not table.show_horizontal_scrollbar
        if not cut:
            from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
            cards=list(app.screen.query(NewsHeroCard))
            assert len(cards)==6
            assert {card.region.height for card in cards}=={9}
            assert len({card.region.y for card in cards})==1
            assert cards[-1].region.right <= viewport.scrollable_content_region.right
            assert text.splitlines()[cards[0].region.y].count('╮')==6
            for label in ('NEWLY LAUNCHED','BEST PLAYS','TOP TRADED','PAIRED LP',
                          'PRICE 24H','VERDICT'):
                assert label in text
            assert app.screen.query_one(TokensTable).region.bottom <= viewport.region.bottom


async def test_small_terminal_advertises_scroll_and_retains_full_table():
    app=SwarmTokensDemo()
    async with app.run_test(size=(100,28)) as pilot:
        await pilot.pause()
        assert '‹ widen' in painted(app) and '‹ taller' in painted(app)
        viewport=app.screen.query_one('#st-viewport',VerticalScroll)
        viewport.scroll_to(x=viewport.max_scroll_x,y=viewport.max_scroll_y,animate=False)
        await pilot.pause()
        assert 'VERDICT' in painted(app)
        assert app.screen.query_one(DataTable).row_count==24


async def test_mock_overview_renders_all_panels_and_every_token_without_network():
    app = SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        text = painted(app)
        for word in ('MOCK DATA','SWARM TOKENS','NEWLY LAUNCHED','BEST PLAYS','TOP TRADED','PAIRED LP'):
            assert word in text
        assert app.screen.query_one(TokensTable).query_one(DataTable).row_count == 24
        assert '* one-sided' in text and 'two-sided' in text
        assert any(char in text for char in '▂▃▄▅▆▇█')


async def test_native_layout_starts_with_heroes_and_standard_panels_have_no_frames():
    app=SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        hero=app.screen.query_one(TokensHero)
        assert hero.region.y <= 1
        assert not app.screen.query('#st-title, #st-selection')
        activity = app.screen.query_one(TopTraded)
        newly = app.screen.query_one(NewlyLaunched)
        plays = app.screen.query_one(BestPlays)
        table = app.screen.query_one(TokensTable)
        assert activity.region.y == newly.region.y == plays.region.y == hero.region.bottom+1
        assert activity.region.right < newly.region.x and newly.region.right < plays.region.x
        assert table.region.y == activity.region.bottom
        lines=painted(app).splitlines()
        heading=next(i for i,line in enumerate(lines) if 'NEWLY LAUNCHED' in line)
        assert lines[heading].index('TOP TRADED') < lines[heading].index('NEWLY LAUNCHED') < lines[heading].index('BEST PLAYS')
        assert next(i for i,line in enumerate(lines) if 'ALL TOKENS' in line) > heading
        assert 'Enter for mock details' not in painted(app)
        assert not any(w.region.width for w in app.screen.query('Input, Select'))
        for kind in (TokensTable,NewlyLaunched,BestPlays,TopTraded):
            panel=app.screen.query_one(kind)
            assert panel.styles.border_top[0] in ('','none')
            assert panel.styles.border_left[0] in ('','none')


async def test_filters_apply_across_panels_and_search_can_return_no_matches():
    app = SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen = app.screen
        await pilot.press('f')
        screen.query_one('#filter-chain',Select).value = 'base'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert screen.snapshot['tokens']
        assert all(row['chain']=='base' for row in screen.snapshot['tokens'])
        assert all(row['chain']=='base' for row in screen.snapshot['newly_launched'])
        ids={row['id'] for row in screen.snapshot['tokens']}
        assert all(event['token_id'] in ids for event in screen.snapshot['activity'])
        assert screen.snapshot['metrics']['total']==len(ids)
        await pilot.press('/')
        screen.query_one('#filter-query',Input).value='no such token'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert screen.snapshot['tokens']==[]
        assert screen.snapshot['activity']==[]
        assert 'No matching tokens' in painted(app)
        await pilot.press('f')
        screen.query_one('#filter-query',Input).value=''
        screen.query_one('#filter-liquidity',Select).value='one-sided'
        await pilot.click('#filter-apply')
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
        await pilot.press('o','o')
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


async def test_filter_draft_cancel_reset_and_shortcut_isolation():
    app=SwarmTokensDemo()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen=app.screen
        await pilot.press('f')
        for label in ('CHAIN','LIQUIDITY','SORT','SEARCH','APPLY FILTER','RESET ALL'):
            assert label in painted(app)
        screen.query_one('#filter-chain',Select).value='base'
        await pilot.pause()
        assert screen.chain=='all' and len(screen.snapshot['tokens'])==24
        await pilot.press('escape')
        assert app.screen is screen
        await pilot.press('f')
        assert screen.query_one('#filter-chain',Select).value=='any'
        screen.query_one('#filter-chain',Select).value='base'
        await pilot.press('f')
        await pilot.pause()
        assert screen.chain=='base'
        await pilot.press('/')
        await pilot.press('f','c','o','m','q','r')
        assert screen.query_one('#filter-query',Input).value=='fcomqr'
        screen.action_refresh()
        await pilot.pause()
        assert screen.query_one('#filter-query',Input).value=='fcomqr'
        assert screen.chain=='base' and screen.sort=='volume'
        await pilot.click('#filter-reset-all')
        await pilot.pause()
        assert screen.chain=='base'  # Reset only changes the draft, as in RECORD.
        assert screen.query_one('#filter-query',Input).value==''
        assert screen.query_one('#filter-chain',Select).value=='any'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert screen.chain=='all' and len(screen.snapshot['tokens'])==24
        assert screen.query_one(TokensTable).query_one(DataTable).has_focus


@pytest.mark.parametrize('width,columns',[(149,4),(100,2)])
@pytest.mark.parametrize('scrolled',[False,True])
async def test_native_filter_grid_fits_the_visible_viewport(width,columns,scrolled):
    from textual.containers import Grid
    from maxpane_dashboard.widgets.swarm_tokens.filter import SwarmTokensFilterEditor
    app=SwarmTokensDemo()
    async with app.run_test(size=(width,45)) as pilot:
        await pilot.pause()
        if scrolled:
            viewport=app.screen.query_one('#st-viewport',VerticalScroll)
            viewport.scroll_to(x=viewport.max_scroll_x,animate=False)
            await pilot.pause()
        await pilot.press('f')
        await pilot.pause()
        editor=app.screen.query_one(SwarmTokensFilterEditor)
        assert editor.query_one(Grid).styles.grid_size_columns==columns
        for field in editor.query('Input, Select'):
            assert field.region.height==1
            assert field.region.right <= width
        text=painted(app)
        for label in ('CHAIN','LIQUIDITY','SORT','SEARCH','APPLY FILTER','RESET ALL'):
            assert label in text


async def test_hub_live_route_returns_with_terminal_draft_and_card_focus():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.widgets.surfboard.rack import SurfboardRack
    app,managers=hub_app()
    from tests.screens.test_swarm_tokens_live import LiveProvider
    provider = LiveProvider()
    managers['_surf_manager'].swarm_tokens_manager = lambda: provider
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
        assert app.screen._data_manager is provider
        assert 'MOCK DATA' not in painted(app)
        assert not managers['_surf_manager'].hub_active
        tokens=app.screen
        await pilot.press('f','escape')
        assert app.screen is tokens
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen is hub
        assert command.value=='status'
        assert rack.focused_card=='swarm-tokens'
        assert managers['_surf_manager'].hub_active


async def test_summary_has_no_idle_scrollbars_and_table_leaves_one_footer_gap():
    from textual.widgets import RichLog
    from maxpane_dashboard.widgets.status_bar import StatusBar
    app = SwarmTokensDemo()
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        for panel in (TopTraded, NewlyLaunched):
            log = screen.query_one(panel).query_one(RichLog)
            assert log.max_scroll_y == 0
            assert not log.show_vertical_scrollbar
        table = screen.query_one(TokensTable)
        summary = screen.query_one('#st-summary')
        footer = screen.query_one(StatusBar)
        assert table.region.y == summary.region.bottom  # remove the former extra row
        assert table.region.bottom == footer.region.y - 1
        assert screen.query_one(DataTable).region.bottom == table.region.bottom
        assert not screen._compositor.render_strips()[footer.region.y - 1].text.strip()
