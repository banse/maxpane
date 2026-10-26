"""Production wallet screen navigation and shared lifecycle, without live I/O."""
from copy import deepcopy
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Input
from maxpane_dashboard.screens.surf_wallet import SurfWalletScreen
from maxpane_dashboard.widgets.surf_wallet import WalletBody
from maxpane_dashboard.data.surf_wallet_models import empty_snapshot
from maxpane_dashboard.screens.wallet_input import WalletInputScreen

WALLET='0x'+'1'*40

class Manager:
    def __init__(self):
        self.payload=empty_snapshot(WALLET); self.calls=0; self.wallet=WALLET
    async def fetch_and_compute(self):
        self.calls+=1; return self.get_snapshot()
    def get_snapshot(self): return {'wallet_snapshot':deepcopy(self.payload)}
    def set_wallet(self,address):
        self.wallet=address; self.payload=empty_snapshot(address); return True
    def is_loading(self,view=None): return False

class Harness(App):
    CSS_PATH=Path(__file__).parents[2]/'maxpane_dashboard/themes/minimal.tcss'
    def __init__(self):
        super().__init__(); self.manager=Manager(); self.view_state={}; self.links=[]
    def on_mount(self): self.push_screen(SurfWalletScreen(self.manager,view_state=self.view_state))
    def open_url(self,url,**kwargs): self.links.append(url)

@pytest.mark.guard
def test_wallet_css_agrees_with_theme():
    css=(Path(__file__).parents[2]/'maxpane_dashboard/themes/minimal.tcss').read_text()
    block=css.split('/* SURF Wallet */',1)[1].split('/* END SURF Wallet */',1)[0]
    assert ' '.join(block.split())==' '.join(SurfWalletScreen.DEFAULT_CSS.split())

async def test_wallet_prompt_cancel_change_and_back_do_not_leak_old_identity(monkeypatch):
    monkeypatch.setattr('maxpane_dashboard.screens.wallet_input.get_wallet',lambda:WALLET)
    monkeypatch.setattr('maxpane_dashboard.screens.wallet_input.save_wallet',lambda address:None)
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause(); screen=app.screen
        assert 'WALLET / SWARM' in screen._compositor.render_strips()[0].text
        await pilot.press('w'); assert isinstance(app.screen,WalletInputScreen)
        await pilot.press('escape'); assert app.screen is screen
        assert app.manager.wallet==WALLET
        await pilot.press('w')
        app.screen.query_one(Input).value='0x'+'2'*40
        await pilot.press('enter'); await pilot.pause()
        assert app.view_state['wallet']=='0x'+'2'*40
        assert WALLET not in '\n'.join(s.text for s in screen._compositor.render_strips())
        screen.query_one(WalletBody).show_view('detail')
        await pilot.press('escape'); assert app.screen is screen and screen.query_one(WalletBody).view=='overview'
        await pilot.press('escape'); assert app.screen is not screen

async def test_boardroom_u_respects_input_and_retains_wallet_view():
    from tests.screens.test_surfboard_screen import hub_app
    app,managers=hub_app(); manager=Manager(); seeds=[]
    def child(wallet=None): seeds.append(wallet); return manager
    managers['_surf_manager'].wallet_manager=child
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause(); hub=app.screen
        await pilot.press('/','u'); assert isinstance(hub.focused,Input) and hub.focused.value=='u'
        assert app.screen is hub
        await pilot.press('escape','u'); await pilot.pause()
        assert isinstance(app.screen,SurfWalletScreen)
        app.screen._wallet_entered('0x'+'2'*40)
        await pilot.press('escape','u'); await pilot.pause()
        assert seeds[-1]=='0x'+'2'*40
        assert app.screen.query_one(WalletBody).view=='overview'

async def test_open_source_revalidates_url_and_index():
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause(); body=app.screen.query_one(WalletBody)
        body.source_links[:]=['https://imd.fun/jobs/test','javascript:alert(1)']
        for index in (0,1,-1,True,'0',99): app.screen.action_open_wallet_source(index)
        assert app.links==['https://imd.fun/jobs/test']

@pytest.mark.parametrize('view',['overview','detail'])
async def test_measured_pins_are_the_first_whole_outer_viewport(view):
    from maxpane_dashboard.screens.surf_wallet import SURF_WALLET_FULL_LAYOUT_COLUMNS as width, SURF_WALLET_FULL_LAYOUT_ROWS as height
    app=Harness()
    async with app.run_test(size=(width,height)) as pilot:
        await pilot.pause(); body=app.screen.query_one(WalletBody); body.show_view(view)
        await pilot.pause(); viewport=body.query_one('#wallet-viewport')
        assert viewport.max_scroll_x==viewport.max_scroll_y==0
        await pilot.resize_terminal(width-1,height); await pilot.pause()
        assert viewport.max_scroll_x>0
        await pilot.resize_terminal(width,height-1); await pilot.pause()
        assert viewport.max_scroll_y>0

async def test_reader_publishes_all_overview_facts_without_opening_detail():
    import asyncio
    from maxpane_dashboard.data.reader import ReaderRuntime
    from maxpane_dashboard.data.surf_wallet_manager import SurfWalletManager
    from tests.data.test_surf_wallet_manager import Swarm, WALLET as live_wallet
    runtime=ReaderRuntime()
    handle=runtime.register('wallet',lambda:SurfWalletManager(swarm=Swarm(),wallet=live_wallet),{'wallet':live_wallet})
    app=Harness(); app.manager=handle
    try:
        async with app.run_test(size=(149,45)) as pilot:
            async with asyncio.timeout(5):
                while not (app.screen.snapshot.get('sources',{}).get('details')):
                    await pilot.pause()
            body=app.screen.query_one(WalletBody)
            assert body.view=='overview'
            assert len(app.screen.snapshot['orders'])==5
            assert app.screen.snapshot['artifacts'] is not None
            assert body.snapshot['wallet']==live_wallet
    finally:
        await runtime.close()
