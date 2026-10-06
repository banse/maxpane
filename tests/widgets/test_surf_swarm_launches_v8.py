import pytest
from copy import deepcopy
from textual.app import App
from textual.widgets import DataTable
from maxpane_dashboard.widgets.surf.swarm_launches import SurfSwarmLaunches
from maxpane_dashboard.widgets.surf.swarm_sites import SurfSwarmSites
from maxpane_dashboard.data.surf_swarm import site_rows
from tests.surf_launch_fixtures import launch_row, fixture
from tests.widgets.surf_compositing import composite_lines
from tests.widgets.address_probe import icon_targets, link_targets


def test_v8_launch_tiers_and_pin_production_before_newer_sepolia():
    panel = SurfSwarmLaunches()
    rows = [launch_row(737, launch_number=1000+i, production=False, chain_id=11155111) for i in range(13)]
    rows += [launch_row(737, launch_number=700+i) for i in range(13)]
    panel.update_data(swarm_launch_rows=rows, swarm_scores_as_of_hhmm='01:02', swarm_launches_as_of_hhmm='03:04')
    kept=panel._payload['rows']
    assert [r['launch_number'] for r in kept] == list(range(712,700,-1))+list(range(1012,1000,-1))
    assert panel._payload['as_of']=='03:04'
    assert tuple(k for k,l,w in panel.column_plan('full',200)) == ('number','ticker','status','chain','token','site','verdict','kind','repo','parked')
    assert tuple(k for k,l,w in panel.column_plan('compact',200)) == ('number','ticker','status','chain','token','site','verdict','parked')
    assert tuple(k for k,l,w in panel.column_plan('tight',100)) == ('number','ticker','status','chain','token','verdict')


@pytest.mark.asyncio
@pytest.mark.parametrize('number', [737,741])
async def test_v8_token_role_beats_distributor_and_markup_is_literal(number):
    row=launch_row(number, ticker='[red]X', verdict={'state':'swarm','passed':4,'failed':None})
    class Harness(App):
        def compose(self): yield SurfSwarmLaunches()
    app=Harness()
    async with app.run_test(size=(190,20)) as pilot:
        panel=app.query_one(SurfSwarmLaunches)
        panel.update_data(swarm_launch_rows=[row]); await pilot.pause()
        text='\n'.join(strip.text for strip in app.screen._compositor.render_strips())
        token=next(a['address'] for a in row['artifacts'] if a['role']=='token')
        assert token in [target for x,y,target in icon_targets(app)]
        assert row['artifacts'][0]['address'] not in [target for x,y,target in icon_targets(app)]
        assert '$[red]X' in text and '◆' in text and '✓ swarm' in text
        assert f'launch-{number}' in text


@pytest.mark.asyncio
async def test_v8_launch_selection_is_subclass_message_and_snapshot():
    class Harness(App):
        selected=None
        def compose(self): yield SurfSwarmLaunches()
        def on_surf_swarm_launches_selected(self,event): self.selected=event.row
    app=Harness(); row=launch_row()
    async with app.run_test(size=(190,20)) as pilot:
        panel=app.query_one(SurfSwarmLaunches); panel.update_data(swarm_launch_rows=[row]); await pilot.pause()
        row['ticker']='changed'
        table=app.query_one(DataTable); table.focus(); await pilot.press('enter'); await pilot.pause()
        assert app.selected['ticker']=='ZTO'
        app.selected=None
        await pilot.click(DataTable, offset=(3,1)); await pilot.pause()
        assert app.selected['launch_number']==737


def test_v8_trusted_site_pins_and_ticker_kept_before_label():
    rows=site_rows(fixture('sites')['sites'])
    row=next(r for r in rows if r['label']=='zto')
    row.update(production_link=True,link_trusted=True,launch_ticker='ZTO',label='a'*40)
    panel=SurfSwarmSites(); panel.update_data(swarm_site_rows=rows,swarm_launches_as_of_hhmm='03:04')
    assert panel._payload['rows'][0] is row
    assert panel._payload['as_of']=='03:04'
    cell=panel.build_cells(row)['label']
    assert '◆' in cell.plain and cell.plain.endswith(' · $ZTO')
    assert cell.style=='bold'
    # A named address match with a different payer must lose the highlight.
    row['link_trusted'] = False
    cell = panel.build_cells(row)['label']
    assert '◆' not in cell.plain and cell.style != 'bold'


@pytest.mark.asyncio
@pytest.mark.parametrize('chain_id,host',[(8453,'basescan.org'),(4663,'robinhoodchain.blockscout.com')])
async def test_v8_launch_and_signal_links_follow_chain_and_literal_ticker(chain_id,host):
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    row=launch_row(chain_id=chain_id,ticker='[red]X')
    address=row['token_address']
    class Harness(App):
        CSS = "SurfSwarmLaunches {height: 10;} SurfSignals {height: auto;}"
        def compose(self):
            yield SurfSwarmLaunches()
            yield SurfSignals()
    app=Harness()
    async with app.run_test(size=(200,35)) as pilot:
        app.query_one(SurfSwarmLaunches).update_data(swarm_launch_rows=[row])
        app.query_one(SurfSignals).update_data(sig_swarm_state='fired',sig_swarm_detail=f'$[red]X #737 BASE ✓ {address}',sig_swarm_age_s=10,sig_swarm_chain_id=chain_id)
        await pilot.pause()
        targets=link_targets(app)
        assert len({y for x,y,n,k,v,url in targets if url==f'https://{host}/address/{address}'})==2
        text='\n'.join(strip.text for strip in app.screen._compositor.render_strips())
        assert text.count('$[red]X')==2
        assert 'SWARM LAUNCH FIRED' in text


@pytest.mark.asyncio
async def test_v8_hero_uses_production_summary_not_window_count():
    from maxpane_dashboard.widgets.surf.swarm_hero import SurfSwarmHero
    from maxpane_dashboard.analytics.surf_swarm_signals import launch_summary
    from maxpane_dashboard.analytics.surf_launch_checks import is_production
    from maxpane_dashboard.data.surf_swarm import launch_rows
    raw=fixture('launches_500')['launches']; rows=launch_rows(raw)
    production={r['id'] for r in raw if is_production(r)}
    for row in rows: row['production']=row['launch_id'] in production
    summary=launch_summary(rows)
    assert sum(e['count'] for e in summary['by_status'])==9
    from tests.widgets.test_surf_swarm_hero import _render
    lines,_,_ = await _render([{'swarm_launch_summary':summary}])
    text='\n'.join(lines)
    assert 'LAUNCHES' in text and '9 live' in text
    assert 'abandoned' not in text


@pytest.mark.asyncio
async def test_v8_missing_ticker_falls_back_to_number_only_for_tokens():
    rows=[launch_row(ticker=None),launch_row(734)]
    text='\n'.join(await composite_lines(SurfSwarmLaunches,(190,20),swarm_launch_rows=rows))
    assert '#737' in text and '#734' not in text
    assert '✓ swarm' in text


@pytest.mark.asyncio
async def test_v8_swarm_signal_sheds_long_ticker_before_launch_number():
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    row=launch_row(ticker='LONGSYMBOL'*6)
    text='\n'.join(await composite_lines(SurfSignals,(53,20),sig_swarm_state='fired',
        sig_swarm_age_s=60,sig_swarm_chain_id=1,
        sig_swarm_detail=f'${row["ticker"]} #737 MAINNET ✓ {row["token_address"]} +3'))
    assert '#737' in text and '$LONG' in text
    assert row['token_address'] not in text


@pytest.mark.asyncio
async def test_v8_launch_copy_and_explorer_clicks_do_not_select():
    class Harness(App):
        selected=None
        copied=None
        opened=None
        def compose(self): yield SurfSwarmLaunches()
        def on_surf_swarm_launches_selected(self,event): self.selected=event.row
        def action_copy_address(self,address): self.copied=address
        def action_open_explorer(self,explorer,kind,value): self.opened=(explorer,kind,value)
    app=Harness(); row=launch_row(site_label='zto')
    async with app.run_test(size=(190,20)) as pilot:
        app.query_one(SurfSwarmLaunches).update_data(swarm_launch_rows=[row]); await pilot.pause()
        x,y,address=icon_targets(app)[0]
        await pilot.click(offset=(x,y)); await pilot.pause()
        assert app.copied==row['token_address'] and app.selected is None
        x,y,explorer,kind,value,url=next(t for t in link_targets(app) if t[3]=='address')
        await pilot.click(offset=(x,y)); await pilot.pause()
        assert app.opened==(explorer,kind,value) and app.selected is None
        x,y,explorer,kind,value,url=next(t for t in link_targets(app) if t[3]=='site')
        assert url=='https://zto.sites.imd.fun/'
        await pilot.click(offset=(x,y)); await pilot.pause()
        assert app.opened==(explorer,kind,value) and app.selected is None
