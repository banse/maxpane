"""Seat selection identity and safely fitted lifetime leaderboard cells."""
from rich.style import Style
from textual.app import App
from textual.widgets import DataTable
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.widgets.surf.swarm_leaderboard import SurfSwarmLeaderboard
from maxpane_dashboard.widgets.fmt import hhmm
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.widgets.surf_compositing import composite_lines
ROWS=fold.board_rows(swarm_capture_v3('contributors'),swarm_capture_v3('workers'))
async def render(rows=ROWS,selected=None,size=(120,18)):
    return '\n'.join(await composite_lines(SurfSwarmLeaderboard,size,
        swarm_board_rows=rows,swarm_seat_selected=selected,
        swarm_board_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02',
        swarm_outcomes_source={'state':'ok','read_ts':1700000000},swarm_contributors_as_of_hhmm='03:01'))
async def test_lifetime_columns_marker_and_two_clocks():
    text=await render(selected={'token_id':ROWS[0]['token_id']})
    for word in ('LEADERBOARD','recorded seats','runtime','dev','att','acc','rej','pend','rate','turns','hrs','state','03:01','04:02'):
        assert word in text
    assert f"▸#{ROWS[0]['token_id']}" in text
    other=await render(selected={'token_id':ROWS[1]['token_id']})
    assert f"▸#{ROWS[1]['token_id']}" in other and f"▸#{ROWS[0]['token_id']}" not in other
async def test_unread_and_empty_are_distinct():
    assert 'unavailable' in await render(None)
    assert 'no submitted records yet' in await render([])
async def test_hostile_runtime_is_sanitized_with_visible_clip():
    text=await render([dict(ROWS[0],runtime='[/x]PWNED'+'x'*64)])
    assert 'PWNED' in text and '…' in text and '‹ widen' in text
    assert '[/x]' not in text
async def test_row_identity_survives_skipped_rows_and_resize():
    class Harness(App):
        def compose(self): yield SurfSwarmLeaderboard()
    async with Harness().run_test(size=(120,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=[None,dict(ROWS[0],token_id=True),dict(ROWS[0],token_id=0),ROWS[1]])
        await pilot.pause()
        for width in (120,90,120):
            await pilot.resize_terminal(width,18);await pilot.pause()
            table=widget.query_one(DataTable)
            assert table.row_count==2
            keys=list(table.rows)
            assert widget.token_for_row(keys[0])==0
            assert widget.token_for_row(keys[1])==ROWS[1]['token_id']

async def test_counters_rate_hours_and_live_state_reach_the_row():
    row=dict(ROWS[0],rank=1,token_id=0,devices=2,attempts=100,accepted=35,rejected=5,
             pending=60,accept_rate=.35,turns=765,wall_clock_s=9000,live_state='working',working=7)
    text=await render([row])
    assert '35.0%' in text and '765' in text and '2.5' in text and '● working 7' in text
    for word in ('100','35','5','60'):assert word in text.split()
    empty=await render([dict(row,attempts=0,accepted=0,accept_rate=None)])
    assert '—' in empty and '0.0%' not in empty

async def test_worker_unavailable_and_offline_are_whole_and_distinct():
    unread=await render([dict(ROWS[0],runtime=None,live_state=None)])
    assert unread.count('unavailable')==2 and 'unavai…' not in unread
    offline=await render([dict(ROWS[0],runtime='offline',live_state='offline')])
    assert offline.count('offline')==2 and 'unavailable' not in offline


async def test_fitting_runtime_with_literal_ellipsis_does_not_claim_clipping():
    for runtime,visible in (("waiting…","waiting…"),("[/x]waiting…","waiting…"),("界界界界界","界界界界界")):
        text=await render([dict(ROWS[0],runtime=runtime)])
        assert visible in text
        assert '‹ widen' not in text.splitlines()[0], text


import copy
import pytest
from rich.color import Color
from maxpane_dashboard.app import CSS_PATH


class SortHarness(App):
    CSS_PATH=CSS_PATH
    def compose(self):yield SurfSwarmLeaderboard()


def tokens(widget):
    return [widget.token_for_row(row.key) for row in widget.query_one(DataTable).ordered_rows]


def _painted_rows(app):
    return [''.join(segment.text for segment in strip) for strip in app.screen._compositor.render_strips()]


@pytest.mark.parametrize('key,field,values',[
    ('rank','rank',(10,2,2,None,None)),
    ('runtime','runtime',('zeta','alpha','alpha',None,None)),
    ('devices','devices',(10,2,2,None,None)),
    ('attempts','attempts',(10,2,2,None,None)),
    ('accepted','accepted',(10,2,2,None,None)),
    ('rejected','rejected',(10,2,2,None,None)),
    ('pending','pending',(10,2,2,None,None)),
    ('rate','accept_rate',(.1,.02,.02,None,None)),
    ('turns','turns',(10,2,2,None,None)),
    ('hours','wall_clock_s',(10,2,2,None,None)),
    ('state','live_state',('working','offline','offline',None,None)),
])
async def test_every_sort_column_is_stable_and_missing_last_both_ways(key,field,values):
    rows=[dict(ROWS[0],token_id=token,rank=index+1,**{}) for index,token in enumerate((101,103,102,104,105))]
    for row,value in zip(rows,values):row[field]=value
    original=copy.deepcopy(rows)
    async with SortHarness().run_test(size=(120,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows)
        widget.sort_by(key)
        # Rank is active on arrival: select another key before asking for rank ascending.
        if key=='rank':widget.reverse_sort()
        await pilot.pause()
        assert tokens(widget)==[103,102,101,104,105]
        widget.reverse_sort();await pilot.pause()
        assert tokens(widget)==[101,103,102,104,105]
        assert rows==original


async def test_seat_sort_is_numeric_and_global_rank_is_not_row_position():
    rows=[dict(ROWS[0],token_id=10,rank=7),dict(ROWS[1],token_id=2,rank=3),dict(ROWS[2],token_id=0,rank=9)]
    async with SortHarness().run_test(size=(120,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows);await pilot.pause()
        assert tokens(widget)==[2,10,0]  # original served rank, regardless of source list order
        widget.sort_by('seat');await pilot.pause()
        assert tokens(widget)==[0,2,10]
        painted=_painted_rows(pilot.app)
        for token,rank in ((0,9),(2,3),(10,7)):
            line=next(line for line in painted if f'#{token} ' in line)
            assert line.split()[0]==str(rank),line
        widget.reverse_sort();await pilot.pause()
        assert tokens(widget)==[10,2,0]


async def test_cursor_token_zero_and_sort_survive_refresh_and_width_tiers():
    rows=[dict(ROWS[0],token_id=10,rank=1,turns=10),dict(ROWS[1],token_id=0,rank=2,turns=2),dict(ROWS[2],token_id=7,rank=3,turns=2)]
    async with SortHarness().run_test(size=(120,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows);await pilot.pause()
        table=widget.query_one(DataTable);table.move_cursor(row=1)
        widget.sort_by('turns');widget.reverse_sort();await pilot.pause()
        assert tokens(widget)==[10,0,7]
        refreshed=[rows[2],dict(rows[0],turns=1),rows[1]]
        widget.update_data(swarm_board_rows=refreshed);await pilot.pause()
        assert tokens(widget)==[7,0,10], 'ties must start from the refreshed source order'
        for width in (120,70,90,120):
            await pilot.resize_terminal(width,18);await pilot.pause()
            assert tokens(widget)[table.cursor_row]==0
            assert tokens(widget)==[7,0,10]
            headers=[str(column.label) for column in table.ordered_columns]
            assert ('turn▼' in headers)==('turns' in widget._keys)


@pytest.mark.parametrize('width',[120,90,70])
async def test_every_sorted_header_marker_fits_existing_fixed_column_width(width):
    widths={'rank':3,'seat':7,'runtime':11,'devices':3,'attempts':5,'accepted':5,
            'rejected':5,'pending':5,'rate':6,'turns':5,'hours':6,'state':16}
    async with SortHarness().run_test(size=(width,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=ROWS[:2]);await pilot.pause()
        for key in widths:
            widget.sort_by(key);await pilot.pause()
            table=widget.query_one(DataTable)
            for column in table.ordered_columns:
                assert column.width==widths[column.key.value]
                assert column.label.cell_len<=column.width
            if key in widget._keys:
                column=table.columns[key]
                assert column.label.plain[-1] in '▲▼'
                header_y=table.region.y
                assert column.label.plain in _painted_rows(pilot.app)[header_y]
            assert table.max_scroll_x==0


@pytest.mark.parametrize('cursor_row',[1,2,3,4,5])
async def test_selected_and_live_states_have_composited_styles(cursor_row):
    states=('idle','working','offline','paused',None,'idle')
    rows=[dict(ROWS[0],token_id=i,rank=i+1,live_state=state,runtime='same',working=3,
               paused_until_ts=1758456000,failures=2) for i,state in enumerate(states)]
    async with SortHarness().run_test(size=(120,18)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows,swarm_seat_selected={'token_id':1});await pilot.pause()
        table=widget.query_one(DataTable);table.focus();table.move_cursor(row=cursor_row)
        await pilot.pause()
        lines=_painted_rows(pilot.app)
        selected_y=next(y for y,line in enumerate(lines) if '▸#1 ' in line)
        rank_x=lines[selected_y].index('2')
        first=pilot.app.screen.get_style_at(rank_x,selected_y)
        assert first.bold and first.color.get_truecolor()==Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
        for column_index,column in enumerate(table.ordered_columns):
            start=sum(c.width+2 for c in table.ordered_columns[:column_index])+table.region.x+1
            assert pilot.app.screen.get_style_at(start,selected_y).bold,(column.key,lines[selected_y])
        for token,word,color in ((1,'working',2),(3,'⏸',1),(4,'unavailable',3)):
            y=next(y for y,line in enumerate(lines) if f'#{token} ' in line)
            style=pilot.app.screen.get_style_at(lines[y].index(word),y)
            assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color],(token,style)
        offline_y=next(y for y,line in enumerate(lines) if '#2 ' in line)
        plain_y=next(y for y,line in enumerate(lines) if '#0 ' in line)
        for index,column in enumerate(table.ordered_columns):
            x=sum(c.width+2 for c in table.ordered_columns[:index])+table.region.x+1
            offline=pilot.app.screen.get_style_at(x,offline_y)
            plain=pilot.app.screen.get_style_at(x,plain_y)
            assert offline.color!=plain.color,(column.key,offline,plain)
        assert 'offline' in lines[offline_y]
        assert widget.token_for_row(table.ordered_rows[1].key)==1


async def test_the_table_has_one_blank_cell_left_and_one_scrollbar_cell_right():
    """Owner, 2026-09-22: the table sits one cell in from the panel's left edge
    (its header one right of the title) and its scrollbar is one cell, so the
    ladder budget (``GUTTER_COLS``) and the BOARD pin are unchanged."""
    async with SortHarness().run_test(size=(120,12)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=ROWS,swarm_board_as_of_hhmm='03:01',
                           swarm_workers_as_of_hhmm='04:02')
        await pilot.pause()
        table=widget.query_one(DataTable)
        assert table.region.x==widget.region.x+1
        assert table.region.right==widget.region.right
        assert table.show_vertical_scrollbar and table.scrollbar_size_vertical==1
        assert widget.GUTTER_COLS==1+table.scrollbar_size_vertical
        painted=_painted_rows(pilot.app)
        title=next(line for line in painted if 'LEADERBOARD' in line)
        header=next(line for line in painted if '#▲' in line)
        assert header.index('#')==title.index('L')+1


def contribution(rows=None, *, state='ok', detail='317/317 production launches', read_ts=1700000000):
    return dict(state=state, read_ts=read_ts, rows=rows, loaded=317, total=317, detail=detail)


@pytest.mark.parametrize('width',[120,106,64,42])
async def test_launch_tab_titles_are_clickable_and_counts_join_only_worker_facts(width):
    rows=[dict(ROWS[0], token_id=10, rank=99, runtime='claude', live_state='working', working=2),
          dict(ROWS[1], token_id=2, rank=18, runtime='codex', live_state='idle')]
    launches=[dict(rank=2, token_id=2, jobs=5, launches=2),
              dict(rank=1, token_id=10, jobs=12, launches=3),
              dict(rank=3, token_id=7, jobs=2, launches=None)]
    original=copy.deepcopy((rows,launches))
    async with SortHarness().run_test(size=(width,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows, swarm_launch_contribution=contribution(launches),
                           swarm_seat_selected={'token_id':10})
        await pilot.pause()
        labels=('recorded','launches') if width==42 else ('recorded seats','launch contribution')
        for mode,word in zip(('recorded','launches'),labels):
            painted=_painted_rows(pilot.app)
            y=next(y for y,line in enumerate(painted) if word in line)
            assert pilot.app.screen.get_style_at(painted[y].index(word),y).meta['@click']==f"screen.board_view('{mode}')"
        widget.set_view('launches');await pilot.pause()
        assert tokens(widget)==[10,2,7]
        table=widget.query_one(DataTable)
        assert 'jobs' in widget._keys and 'turns' not in widget._keys
        painted=_painted_rows(pilot.app)
        first=next(line for line in painted if '▸#10 ' in line)
        assert first.split()[:3]==['1','▸#10','12']
        if 'runtime' in widget._keys:
            assert 'claude' in first
        if 'state' in widget._keys:
            assert '● working 2' in first
        unknown=next(line for line in painted if '#7 ' in line)
        assert '—' in unknown and 'unavailable' not in unknown
        assert table.max_scroll_x==0
        assert (rows,launches)==original


@pytest.mark.parametrize('state,rows,word',[
    ('pending',None,'loading'),('failed',None,'load failed'),
    ('ok',[],'no launch contributions'),('partial',[],'no confirmed contributions'),
])
async def test_launch_tab_distinguishes_loading_failed_empty_and_partial(state,rows,word):
    async with SortHarness().run_test(size=(106,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution(rows,state=state,
            detail='17/317 production launches',read_ts=None))
        widget.set_view('launches');await pilot.pause()
        text='\n'.join(_painted_rows(pilot.app))
        assert word in text and '17/317 production launches' in text
        assert not tokens(widget)
        if state=='failed':
            y=next(y for y,line in enumerate(_painted_rows(pilot.app)) if 'load failed' in line)
            x=_painted_rows(pilot.app)[y].index('load failed')
            assert pilot.app.screen.get_style_at(x,y).color.get_truecolor()==Color.parse('#ff0000').get_truecolor()


@pytest.mark.parametrize('state',['pending','partial','stale','failed'])
async def test_launch_refresh_retains_snapshot_and_source_clock_without_loading(state):
    rows=[dict(rank=1,token_id=7,jobs=12,launches=3)]
    async with SortHarness().run_test(size=(106,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution(rows))
        widget.set_view('launches');await pilot.pause()
        before=_painted_rows(pilot.app)
        widget.update_data(swarm_launch_contribution=contribution(rows,state=state,
            detail='17/317 production launches · retry'))
        await pilot.pause()
        painted=_painted_rows(pilot.app)
        assert next(line for line in painted if '#7 ' in line)==next(line for line in before if '#7 ' in line)
        text='\n'.join(painted)
        assert '17/317 production launches' in text and hhmm(1700000000) in text
        assert 'loading' not in text
        if state in ('failed','stale'):assert 'load failed' in text


async def test_launch_and_recorded_views_keep_independent_sort_cursor_and_scroll():
    rows=[dict(ROWS[0],token_id=i,rank=i+1,turns=40-i) for i in range(40)]
    launches=[dict(rank=i+1,token_id=i,jobs=40-i,launches=None if i==5 else i%4)
              for i in range(40)]
    async with SortHarness().run_test(size=(106,12)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=rows,swarm_launch_contribution=contribution(launches))
        await pilot.pause()
        table=widget.query_one(DataTable)
        widget.sort_by('turns');await pilot.pause()
        table.move_cursor(row=20);await pilot.pause()
        recorded_token=tokens(widget)[table.cursor_row]
        recorded_scroll=table.scroll_y
        widget.set_view('launches');await pilot.pause()
        widget.sort_by('launches');widget.reverse_sort();await pilot.pause()
        assert tokens(widget)[-1]==5
        table.move_cursor(row=25);await pilot.pause()
        launch_token=tokens(widget)[table.cursor_row]
        launch_scroll=table.scroll_y
        widget.sort_by('turns')  # This column is not part of the contribution schema.
        assert widget._sort_key=='launches'
        widget.set_view('recorded');await pilot.pause()
        assert (widget._sort_key,widget._sort_reverse)==('turns',False)
        assert tokens(widget)[table.cursor_row]==recorded_token
        assert table.scroll_y==recorded_scroll
        widget.update_data(swarm_board_rows=list(reversed(rows)),swarm_launch_contribution=contribution(list(reversed(launches))))
        await pilot.pause()
        assert tokens(widget)[table.cursor_row]==recorded_token
        assert table.scroll_y==recorded_scroll
        widget.set_view('launches');await pilot.pause()
        assert (widget._sort_key,widget._sort_reverse)==('launches',True)
        assert tokens(widget)[table.cursor_row]==launch_token
        assert table.scroll_y==launch_scroll
        widget.cycle_sort();await pilot.pause()
        assert widget._sort_key=='build_review'


async def test_launch_progress_updates_preserve_recorded_rows_clocks_and_worker_join():
    row=dict(ROWS[0],token_id=7,rank=1,runtime='codex',live_state='working',working=2)
    async with SortHarness().run_test(size=(106,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=[row],swarm_seat_selected={'token_id':7},
                           swarm_workers_as_of_hhmm='01:23')
        await pilot.pause()
        recorded=_painted_rows(pilot.app)
        widget.set_launch_contribution(contribution(None,state='pending',detail='1/317 production launches'))
        await pilot.pause()
        assert _painted_rows(pilot.app)==recorded
        widget.set_view('launches');await pilot.pause()
        widget.set_launch_contribution(contribution(None,state='pending',detail='2/317 production launches'))
        await pilot.pause()
        assert '2/317 production launches' in '\n'.join(_painted_rows(pilot.app))
        widget.set_launch_contribution(contribution([dict(rank=1,token_id=7,jobs=12,launches=3)]))
        await pilot.pause()
        launch_row=next(line for line in _painted_rows(pilot.app) if '▸#7 ' in line)
        assert '12' in launch_row and 'codex' in launch_row and 'working 2' in launch_row
        widget.set_view('recorded');await pilot.pause()
        assert _painted_rows(pilot.app)==recorded


@pytest.mark.parametrize('width',[21,51,52,53,106])
async def test_leaderboard_title_keeps_both_tabs_clickable_and_widen_visible_at_narrow_widths(width):
    async with SortHarness().run_test(size=(width,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=ROWS)
        await pilot.pause()
        title=widget.query_one('.panel-title')
        painted=_painted_rows(pilot.app)[title.region.y]
        actions={pilot.app.screen.get_style_at(x,title.region.y).meta.get('@click')
                 for x in range(title.region.x,title.region.right) if painted[x]!=' '}
        assert {"screen.board_view('recorded')","screen.board_view('launches')"}<=actions
        assert title.region.height==1
        assert ('‹' in painted)==bool(widget._widen or widget._clipped)
        if width==106:
            assert 'LEADERBOARD · recorded seats · launch contribution' in painted


async def test_launch_model_effort_and_build_review_paint_paired_current_settings():
    pairs=[{'model':'claude-fable-5-1','effort':'high'},
           {'model':'gpt-6-astra','effort':'xhigh'}]
    launches=[dict(rank=1,token_id=10,jobs=12,launches=3,build_jobs=3,review_jobs=10,
                   advertised_models=pairs),
              dict(rank=2,token_id=2,jobs=4,launches=2,build_jobs=0,review_jobs=4,
                   advertised_models=[]),
              dict(rank=3,token_id=7,jobs=2,launches=1,build_jobs=None,review_jobs=None,
                   advertised_models=None)]
    original=copy.deepcopy(launches)
    async with SortHarness().run_test(size=(120,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution(launches))
        widget.set_view('launches');await pilot.pause()
        painted=_painted_rows(pilot.app)
        assert all(word in painted[widget.query_one(DataTable).region.y]
                   for word in ('model','effort','build/review'))
        first=next(line for line in painted if '#10 ' in line)
        assert 'fable 5.1 +1' in first and 'high' in first.split() and '3 / 10' in first
        second=next(line for line in painted if '#2 ' in line)
        assert '0 / 4' in second
        third=next(line for line in painted if '#7 ' in line)
        assert '— / —' in third
        assert 'unavailable' not in '\n'.join(painted)
        assert launches==original


@pytest.mark.parametrize('key,values',[
    ('model',[
        {'advertised_models':[{'model':'claude-fable-5-1','effort':'high'}]},
        {'advertised_models':[{'model':'gpt-6-astra','effort':'xhigh'}]},
        {'advertised_models':[{'model':'gpt-6-astra','effort':None}]},
        {'advertised_models':[]}, {'advertised_models':None}]),
    ('effort',[
        {'advertised_models':[{'model':'gpt-6-astra','effort':'xhigh'}]},
        {'advertised_models':[{'model':'claude-fable-5-1','effort':'high'}]},
        {'advertised_models':[{'model':'claude-fable-5-1','effort':'high'}]},
        {'advertised_models':[{'model':'gpt-6-astra','effort':None}]},
        {'advertised_models':None}]),
    ('build_review',[
        {'build_jobs':10,'review_jobs':2}, {'build_jobs':2,'review_jobs':10},
        {'build_jobs':2,'review_jobs':10}, {'build_jobs':None,'review_jobs':2},
        {'build_jobs':0,'review_jobs':None}]),
])
async def test_launch_new_columns_sort_stably_with_missing_last(key,values):
    rows=[dict(rank=i+1,token_id=token,jobs=12,launches=2,**value)
          for i,(token,value) in enumerate(zip((101,103,102,104,105),values))]
    async with SortHarness().run_test(size=(120,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution(rows))
        widget.set_view('launches')
        widget.sort_by(key);await pilot.pause()
        assert tokens(widget)==[103,102,101,104,105]
        widget.reverse_sort();await pilot.pause()
        assert tokens(widget)==[101,103,102,104,105]
        header=widget.query_one(DataTable).columns[key]
        assert header.label.plain in _painted_rows(pilot.app)[widget.query_one(DataTable).region.y]


async def test_launch_tooltip_follows_actual_hover_and_keyboard_row_without_model_guessing():
    pairs=[{'model':'claude-fable-5-1','effort':'high'},
           {'model':'gpt-6-astra[/x]','effort':'xhigh\x1b'}]
    rows=[dict(rank=1,token_id=10,jobs=12,launches=3,build_jobs=3,review_jobs=10,
               advertised_models=pairs),
          dict(rank=2,token_id=2,jobs=4,launches=2,build_jobs=0,review_jobs=4,
               advertised_models=None)]
    async with SortHarness().run_test(size=(120,18),tooltips=True) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_board_rows=[dict(ROWS[0],token_id=2,runtime='claude')],
                           swarm_launch_contribution=contribution(rows))
        widget.set_view('launches');await pilot.pause()
        table=widget.query_one(DataTable)
        table.move_cursor(row=1);await pilot.pause()
        await pilot.hover(table,offset=(3,1));await pilot.pause()
        assert table.cursor_row==1  # Hover must use the row under the pointer.
        tooltip=table.tooltip
        assert 'Current advertised settings' in tooltip.plain
        assert 'claude-fable-5-1 · high' in tooltip.plain
        assert 'gpt-6-astra · xhigh' in tooltip.plain
        assert 'Build/review' in tooltip.plain and 'overlap' in tooltip.plain
        assert not tooltip.spans and '\x1b' not in tooltip.plain and '[/x]' not in tooltip.plain
        widget.set_launch_contribution(contribution(rows,state='pending'))
        await pilot.pause()
        assert 'claude-fable-5-1 · high' in table.tooltip.plain
        pilot.app.screen._handle_tooltip_timer(table)
        await pilot.pause()
        assert 'Current advertised settings' in '\n'.join(_painted_rows(pilot.app))
        pilot.app.screen._clear_tooltip()
        table.focus();await pilot.press('up','down');await pilot.pause()
        assert 'Current advertised settings unavailable' in table.tooltip.plain
        widget.set_view('recorded');await pilot.pause()
        assert table.tooltip is None


async def test_launch_long_model_preserves_additional_pair_count_and_marks_clipping():
    pairs=[{'model':'aaa-model-'+'界'*20+'[/x]', 'effort':'high'},
           {'model':'gpt-6-astra', 'effort':'xhigh'}]
    async with SortHarness().run_test(size=(120,14)) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution([
            dict(rank=1,token_id=10,jobs=12,launches=3,build_jobs=3,review_jobs=10,
                 advertised_models=pairs)]))
        widget.set_view('launches');await pilot.pause()
        painted=_painted_rows(pilot.app)
        row=next(line for line in painted if '#10 ' in line)
        assert '… +1' in row and '[/x]' not in row
        assert '‹ widen' in '\n'.join(painted)


@pytest.mark.parametrize('models,label',[
    (None,'Current advertised settings unavailable'),
    ([], 'No current advertised settings'),
])
async def test_launch_hover_distinguishes_unavailable_from_no_advertised_models(models,label):
    async with SortHarness().run_test(size=(120,18),tooltips=True) as pilot:
        widget=pilot.app.query_one(SurfSwarmLeaderboard)
        widget.update_data(swarm_launch_contribution=contribution([
            dict(rank=1,token_id=7,jobs=2,launches=1,build_jobs=2,review_jobs=0,
                 advertised_models=models)]))
        widget.set_view('launches');await pilot.pause()
        table=widget.query_one(DataTable)
        await pilot.hover(table,offset=(3,1));await pilot.pause()
        pilot.app.screen._handle_tooltip_timer(table)
        await pilot.pause()
        assert label in ' '.join('\n'.join(_painted_rows(pilot.app)).split())
