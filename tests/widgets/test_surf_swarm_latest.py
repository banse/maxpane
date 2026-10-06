"""The upcoming LATEST LAUNCHES input contract, frozen before its WP3 renderer."""
from maxpane_dashboard.data import surf_models as models


def test_latest_and_throughput_signatures_are_frozen_before_mount_switch():
    assert models.SWARM_LATEST_LAUNCHES_SIGNATURE == (
        'swarm_launch_rows', 'swarm_launches_as_of_hhmm', 'as_of')
    assert models.SWARM_THROUGHPUT_SIGNATURE == (
        'swarm_throughput', 'swarm_as_of_hhmm', 'swarm_stale')


from copy import deepcopy
import pytest
from textual.app import App
from textual.widgets import DataTable
from tests.surf_launch_fixtures import launch_row, fixture
from tests.widgets.surf_compositing import composite_lines


def latest_rows():
    from maxpane_dashboard.data.surf_swarm import launch_rows
    from maxpane_dashboard.analytics.surf_launch_checks import is_production
    raw = fixture('launches_100')['launches']
    rows = launch_rows(raw)
    for row, original in zip(rows, raw):
        row['production'] = is_production(original)
    return rows


async def test_latest_orders_created_time_not_number_and_excludes_sepolia():
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    rows = latest_rows()
    # The captured #747 is newer than #751. Retain five production witnesses.
    rows = [r for r in rows if r['launch_number'] in (751,747,741,740,737) or not r['production']]
    expected = sorted((r for r in rows if r['production']),
        key=lambda r:(r['created_ts'],r['launch_number']), reverse=True)[:5]
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46,12)) as pilot:
        panel=pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=rows,swarm_launches_as_of_hhmm='14:16',as_of=2000000000.)
        await pilot.pause()
        text='\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
        assert [r['launch_number'] for r in panel._selection_rows] == [r['launch_number'] for r in expected]
        assert len(panel._selection_rows)==5 and text.index('#747')<text.index('#751')
        assert 'SEPOLIA' not in text and 'LATEST LAUNCHES' in text
        assert all('#'+str(r['launch_number']) in text for r in expected)
        assert panel.top_row()['launch_number']==747


@pytest.mark.parametrize('opening',['click','enter'])
async def test_latest_selection_opens_immutable_popup_snapshot(opening):
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
        def on_surf_swarm_latest_launches_selected(self,event):
            self.push_screen(LaunchDetailScreen(event.row))
    row=launch_row(ticker='[red]X')
    async with Probe().run_test(size=(46,30)) as pilot:
        panel=pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=[row],as_of=row['created_ts']+120)
        await pilot.pause()
        row['ticker']='changed'
        table=panel.query_one(DataTable)
        if opening=='click': await pilot.click(table,offset=(3,0))
        else:
            table.focus()
            await pilot.press('enter')
        await pilot.pause()
        assert isinstance(pilot.app.screen,LaunchDetailScreen)
        assert pilot.app.screen.row['ticker']=='[red]X'
        assert pilot.app.screen.row['as_of']==row['created_ts']+120


@pytest.mark.parametrize('width,chain,age',[(46,True,True),(37,True,False),(29,False,False),(19,False,False)])
async def test_latest_width_sheds_age_then_chain_before_identity(width,chain,age):
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    row=launch_row(ticker='LONGSYMBOL'*4)
    text='\n'.join(await composite_lines(SurfSwarmLatestLaunches,(width,12),swarm_launch_rows=[row],as_of=row['created_ts']+180))
    assert '#737' in text and '✓ swarm' in text
    assert ('MAINNET' in text)==chain
    assert ('3m' in text)==age


@pytest.mark.parametrize('rows,word',[(None,'unavailable'),([], 'no production launch yet'),([launch_row(production=False)],'no production launch yet')])
async def test_latest_empty_and_unavailable(rows,word):
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    text='\n'.join(await composite_lines(SurfSwarmLatestLaunches,(46,12),swarm_launch_rows=rows))
    assert word in text


async def test_latest_pending_verdict_keeps_full_words_before_ticker():
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    row=launch_row(ticker='LONGSYMBOL',verdict={'state':'not_deployed','passed':0,'failed':None})
    text='\n'.join(await composite_lines(SurfSwarmLatestLaunches,(29,12),swarm_launch_rows=[row]))
    assert '#737' in text and '-- pending' in text


@pytest.mark.parametrize('seconds,word',[(0,'<1m'),(60,'1m'),(3600,'1h'),(86400,'1d')])
async def test_latest_age_uses_snapshot_clock_and_literal_symbol(seconds,word):
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    row=launch_row(ticker='[red]X')
    text='\n'.join(await composite_lines(SurfSwarmLatestLaunches,(46,12),swarm_launch_rows=[row],as_of=row['created_ts']+seconds))
    assert '$[red]X' in text and word in text and '\\' not in text


async def test_latest_caps_more_than_five_production_launches():
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    rows = [dict(launch_row(), launch_number=737+i, created_ts=1000+i) for i in range(7)]
    class Probe(App):
        def compose(self): yield SurfSwarmLatestLaunches()
    async with Probe().run_test(size=(46, 14)) as pilot:
        panel = pilot.app.query_one(SurfSwarmLatestLaunches)
        panel.update_data(swarm_launch_rows=rows, as_of=2000)
        await pilot.pause()
        text = '\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
        assert len(panel._payload['rows']) == panel.query_one(DataTable).row_count == 5
        assert all(f'#{number}' in text for number in range(739, 744))
        assert '#738' not in text and '#737' not in text


@pytest.mark.parametrize('width', [20, 28, 32, 33, 46])
@pytest.mark.parametrize('rows,word', [(None, 'unavailable'), ([], 'no production launch yet'),
                                     ([launch_row()], '#737')])
async def test_latest_title_and_first_content_row(width, rows, word):
    from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
    lines = await composite_lines(SurfSwarmLatestLaunches, (width, 14),
        swarm_launch_rows=rows, swarm_launches_as_of_hhmm='14:16')
    assert 'LATEST LAUNCHES' in lines[0]
    assert not lines[1].strip()
    assert (word if width >= 28 else word[:12]) in lines[2]
    if width < 31:
        assert '…' in lines[0]
