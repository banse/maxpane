"""Mounted liquidity cells and popup evidence from the committed pool captures."""
from copy import deepcopy

import pytest
from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Static, DataTable

from maxpane_dashboard.analytics import surf_launch_liquidity as ll
from maxpane_dashboard.data.surf_swarm import launch_rows
from maxpane_dashboard.screens.swarm_detail import LaunchDetailScreen
from maxpane_dashboard.widgets.surf.swarm_launches import SurfSwarmLaunches
from tests.analytics.test_surf_launch_liquidity import live_fixture, fixture, pool_fixture
from tests.surf_launch_fixtures import launch_row, launch_event
from tests.widgets.surf_compositing import composite_lines
from tests.widgets.address_probe import icon_targets, link_targets


def liquid_row(number=737, **changes):
    raw,pool,answers,decimals=live_fixture(number)
    liquidity=ll.liquidity_result(raw,pool,[answers[i] for i in range(3)],decimals,
        fixture(number,'launch_policies')['policies'],{'K2':{'evidence':{'transactions':[{'to':next(iter(pool_fixture(number)[1].values()))['to']}]}}},now=1791300000.)
    liquidity.update(changes)
    row=launch_row(number) if number in (737,747) else launch_rows([raw])[0]
    row.update(launch_number=number,production=True,ticker=raw.get('manifest',{}).get('token',{}).get('symbol') or row.get('ticker'),
        liquidity=liquidity,pool_fee=liquidity['pool_fee'],verdict={'state':'swarm','passed':4,'failed':None},as_of=1791300600.)
    row['checks']=dict(row.get('checks') or {}, K8=liquidity)
    return row


@pytest.mark.parametrize('number,word',[(737,'4.7K IMD'),(747,'no liq'),(775,'14.2 ETH'),(791,'0.1 IMD')])
async def test_liquidity_cells_from_capture(number,word):
    text='\n'.join(await composite_lines(SurfSwarmLaunches,(210,14),swarm_launch_rows=[liquid_row(number)]))
    assert 'liq' in text and word in text


async def test_withdrawn_liquidity_is_red_and_keeps_swarm_verdict():
    class Probe(App):
        def compose(self): yield SurfSwarmLaunches()
    row=liquid_row(lock='withdrawn',withdrawn_pct=50,state='warn')
    async with Probe().run_test(size=(210,14)) as pilot:
        pilot.app.query_one(SurfSwarmLaunches).update_data(swarm_launch_rows=[row])
        pilot.app.query_one(DataTable).show_cursor=False
        await pilot.pause()
        strips=pilot.app.screen._compositor.render_strips()
        text='\n'.join(s.text for s in strips)
        assert 'withdrawn' in text and '✓ swarm' in text
        segments=[seg for strip in strips for seg in strip if 'withdrawn' in seg.text]
        assert segments and all(seg.style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[1] for seg in segments)
        verdicts = [seg for strip in strips for seg in strip if '✓ swarm' in seg.text]
        assert verdicts and all(seg.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[2]
                                for seg in verdicts)


def test_liquidity_tier_priority_and_degraded_cells():
    panel=SurfSwarmLaunches()
    assert 'liq' in [k for k,l,w in panel.column_plan('full',210)]
    for tier, budget in [('compact',107), ('compact',120), ('compact',138), ('roomy',151)]:
        keys = [k for k,l,w in panel.column_plan(tier,budget)]
        assert keys[keys.index('verdict')+1] == 'liq'
        assert 'kind' not in keys
        if tier == 'compact':
            assert 'site' not in keys and 'repo' not in keys
    assert 'liq' in [k for k,l,w in panel.column_plan('tight',100)]
    assert 'liq' not in [k for k,l,w in panel.column_plan('tight',72)]
    for row,word in [(liquid_row(state='unknown'),'…'),(liquid_row(state='na'),'--'),
                     (dict(liquid_row(),production=False),'--'),(liquid_row(range_state='token only'),'one-sided')]:
        assert panel.build_cells(row)['liq'].plain==word


@pytest.mark.parametrize('number,fee,amount',[(737,'1.25%','4,726.59 IMD'),(747,'1.25%','at limit'),(775,'0.3%','14.23 ETH'),(791,'1.25%','0.1013 IMD')])
async def test_popup_descriptions_fee_and_k8_evidence(number,fee,amount):
    class Probe(App): pass
    row=liquid_row(number)
    async with Probe().run_test(size=(110,40)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row)); await pilot.pause()
        scroll=pilot.app.screen.query_one(VerticalScroll)
        seen=''; icons=set();links=set()
        while True:
            seen+='\n'+'\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
            icons.update(a for x,y,a in icon_targets(pilot.app));links.update(v[5] for v in link_targets(pilot.app))
            if scroll.scroll_y>=scroll.max_scroll_y: break
            scroll.scroll_relative(y=15,animate=False);await pilot.pause()
        for word in ('a launch row on a production chain',"deployed by the swarm's launch wallet",
                     "deployed code matches the swarm's attested build", "passed the swarm's admission checks",
                     'who holds the pool liquidity','outside audits or bounties on record',
                     'pool liquidity: paired amount, range, lock',fee,amount,'never withdrawn (L = deployed L)',
                     'in factory','(unverified)','as of','10m ago'):
            assert word in seen,(word,seen)
        assert row['liquidity']['owner'] in icons and 'burned' not in seen
        host='robinhoodchain.blockscout.com' if number==791 else 'etherscan.io'
        assert f"https://{host}/address/{row['liquidity']['owner']}" in links
        if number!=747: assert '100% of active liquidity' in seen


async def test_popup_narrow_heading_clips_description_first_and_unknown_fee():
    class Probe(App): pass
    row=launch_row(747,pool_fee=None)
    async with Probe().run_test(size=(42,40)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row));await pilot.pause()
        heading=pilot.app.screen.query_one('#launch-check-K3',Static)
        scroll=pilot.app.screen.query_one(VerticalScroll)
        scroll.scroll_to_widget(heading,animate=False);await pilot.pause()
        text='\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
        line=next(line for line in text.splitlines() if 'K3 ·' in line)
        assert 'K3 · pass (immutables)' in line and '…' in line
        assert heading.size.height==1


async def test_detector_multiple_active_fired_count_reaches_mounted_row():
    from maxpane_dashboard.analytics.surf_signals import build_signals
    from maxpane_dashboard.widgets.surf.signals import SurfSignals
    events=[launch_event(737),launch_event(747)]
    _,base=build_signals({}, {'swarm_launch_events':{'events':[],'ts':1000.}},1000.)
    signals,_=build_signals(base,{'swarm_launch_events':{'events':events,'ts':1001.}},1001.)
    assert signals['sig_swarm_state']=='fired'
    assert signals['sig_swarm_launch']['extra_count']==len(signals['swarm_launch_fired'])-1==1
    text='\n'.join(await composite_lines(SurfSignals,(110,30),**signals))
    assert '+1' in next(line for line in text.splitlines() if 'SWARM LAUNCH' in line)


async def test_roomy_sheds_kind_before_liquidity_in_mounted_ladder():
    from maxpane_dashboard.widgets.surf.swarm_launches import FULL_WIDTH
    text='\n'.join(await composite_lines(SurfSwarmLaunches,(FULL_WIDTH+1,14),swarm_launch_rows=[liquid_row()]))
    header=next(line for line in text.splitlines() if 'ticker' in line)
    assert 'repo' in header and 'liq' in header and 'kind' not in header
    assert '4.7K IMD' in text
    assert 'launch-737' in text


@pytest.mark.parametrize('factory', [False, None])
async def test_nonfactory_lock_does_not_claim_unverified_contract(factory):
    class Probe(App): pass
    row = liquid_row(owner_is_factory=factory)
    async with Probe().run_test(size=(110, 40)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row))
        await pilot.pause()
        pilot.app.screen.query_one(VerticalScroll).scroll_end(animate=False)
        await pilot.pause()
        text = '\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
        line = next(line for line in text.splitlines() if 'never withdrawn' in line)
        assert 'held by' in line and '(unverified)' not in line
        assert '(L = deployed L)' in line


@pytest.mark.parametrize('has_code,matching,annotated', [(True,True,True), (False,True,False),
                                                       (None,True,False), (True,False,False)])
async def test_nonfactory_lock_uses_cached_owner_code(has_code, matching, annotated):
    class Probe(App): pass
    row = liquid_row(owner_is_factory=False)
    owner = row['liquidity']['owner']
    row['checks']['K6'] = {'state':'info', 'evidence': {
        'owner': owner if matching else '0x' + '1' * 40, 'owner_has_code':has_code}}
    async with Probe().run_test(size=(110, 40)) as pilot:
        await pilot.app.push_screen(LaunchDetailScreen(row)); await pilot.pause()
        pilot.app.screen.query_one(VerticalScroll).scroll_end(animate=False)
        await pilot.pause()
        text = '\n'.join(s.text for s in pilot.app.screen._compositor.render_strips())
        line = next(line for line in text.splitlines() if 'never withdrawn' in line)
        assert 'held by' in line and '(unverified)' not in line
        assert ('(contract)' in line) == annotated
