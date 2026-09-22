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
