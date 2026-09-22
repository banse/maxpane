"""Seat selection identity and safely fitted lifetime leaderboard cells."""
from rich.style import Style
from textual.app import App
from textual.widgets import DataTable
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.widgets.surf.swarm_leaderboard import SurfSwarmLeaderboard
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.widgets.surf_compositing import composite_lines
ROWS=fold.board_rows(swarm_capture_v3('contributors'),swarm_capture_v3('workers'))
async def render(rows=ROWS,selected=None,size=(120,18)):
    return '\n'.join(await composite_lines(SurfSwarmLeaderboard,size,
        swarm_board_rows=rows,swarm_seat_selected=selected,
        swarm_board_as_of_hhmm='03:01',swarm_workers_as_of_hhmm='04:02'))
async def test_lifetime_columns_marker_and_two_clocks():
    text=await render(selected={'token_id':ROWS[0]['token_id']})
    for word in ('LEADERBOARD','lifetime','runtime','dev','att','acc','rej','pend','rate','turns','hrs','state','03:01','04:02'):
        assert word in text
    assert f"▸#{ROWS[0]['token_id']}" in text
    other=await render(selected={'token_id':ROWS[1]['token_id']})
    assert f"▸#{ROWS[1]['token_id']}" in other and f"▸#{ROWS[0]['token_id']}" not in other
async def test_unread_and_empty_are_distinct():
    assert 'unavailable' in await render(None)
    assert 'no contributors yet' in await render([])
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
