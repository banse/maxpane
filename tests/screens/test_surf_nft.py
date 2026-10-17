"""NFT screen interaction uses cached facts; refresh is the I/O boundary."""
from copy import deepcopy
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable, Input, Select

from maxpane_dashboard.screens.surf_nft import SurfNftScreen
from maxpane_dashboard.widgets.surf_nft import NftTable, NftDetail
from tests.widgets.test_surf_nft import snapshot, painted


class Manager:
    def __init__(self):
        self.payload=snapshot(); self.calls=0; self.selections=[]
    async def fetch_and_compute(self):
        self.calls+=1
        return deepcopy(self.payload)
    def get_snapshot(self):
        return deepcopy(self.payload)
    def select(self,identity):
        self.selections.append(identity)
    def is_loading(self,view=None):
        return False


class Harness(App):
    CSS_PATH=Path(__file__).parents[2]/'maxpane_dashboard/themes/minimal.tcss'
    def __init__(self,manager=None):
        super().__init__(); self.manager=manager or Manager()
    def on_mount(self):
        self.push_screen(SurfNftScreen(self.manager))


@pytest.mark.guard
def test_screen_css_agrees_with_production_theme():
    css=(Path(__file__).parents[2]/'maxpane_dashboard/themes/minimal.tcss').read_text()
    block=css.split('/* SURF NFT Explorer */',1)[1].split('/* END SURF NFT Explorer */',1)[0]
    assert ' '.join(block.split())==' '.join(SurfNftScreen.DEFAULT_CSS.split())


async def test_cached_idmd_mint_filters_search_and_stage_never_fetch():
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen=app.screen; count=app.manager.calls
        await pilot.press('f')
        screen.query_one('#filter-idmd',Select).value='yes'
        screen.query_one('#filter-mint',Select).value='open'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert screen.snapshot['nft_rows']
        assert all(r['idmd_benefit']['status']=='yes' and r['mint']['state']=='open' for r in screen.snapshot['nft_rows'])
        assert app.manager.calls==count
        await pilot.press('/')
        screen.query_one('#filter-search',Input).value='not-a-collection'
        await pilot.click('#filter-apply')
        await pilot.pause()
        assert 'No matching collections' in painted(app)
        assert app.manager.calls==count
        screen.filters.update(idmd='all',mint='all',search='')
        screen.action_stage()
        await pilot.pause()
        assert screen.query_one(NftTable).stage=='building'
        assert screen.snapshot['nft_summary']['deployed']==len(app.manager.payload['nft_rows'])
        assert app.manager.calls==count


async def test_selection_enter_detail_and_cancel_preserve_view_without_fetch():
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen=app.screen; table=screen.query_one(DataTable); calls=app.manager.calls
        table.move_cursor(row=2)
        await pilot.pause()
        chosen=screen.query_one(NftTable).selected_row()['id']
        await pilot.press('enter')
        assert screen.focused is screen.query_one(NftDetail)
        assert screen.snapshot['nft_selected']['id']==chosen
        assert app.manager.selections[-1]==chosen
        await pilot.press('f')
        screen.query_one('#filter-idmd',Select).value='no'
        await pilot.press('escape')
        assert app.screen is screen and screen.filters['idmd']=='all'
        assert screen.snapshot['nft_selected']['id']==chosen
        assert app.manager.calls==calls
        await pilot.press('/')
        await pilot.press('n','p','f','r')
        assert screen.query_one('#filter-search',Input).value=='npfr'
        await pilot.press('escape')
        assert app.screen is screen
        await pilot.press('escape')
        assert app.screen is not screen


async def test_hub_nfts_and_protocol_keys_preserve_input_and_retained_state():
    from tests.screens.test_surfboard_screen import hub_app
    from maxpane_dashboard.screens.surf import MODE_POOL4, SurfScreen
    from maxpane_dashboard.widgets.surfboard import SurfboardRack
    app,managers=hub_app()
    manager=Manager()
    managers['_surf_manager'].nft_manager=lambda:manager
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        hub=app.screen
        await pilot.press('/')
        field=hub.focused
        await pilot.press('n','p')
        assert isinstance(field,Input) and field.value=='np'
        assert app.screen is hub
        await pilot.press('escape','n')
        await pilot.pause()
        assert isinstance(app.screen,SurfNftScreen)
        app.screen.action_chain()
        await pilot.press('escape','n')
        await pilot.pause()
        assert app.screen.filters['chain']=='ethereum'
        await pilot.press('escape','p')
        await pilot.pause()
        assert isinstance(app.screen,SurfScreen) and app.screen._mode==MODE_POOL4
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen is hub
        rack=hub.query_one(SurfboardRack)
        rack.focused_card='surf-nft'
        rack.focus_card()
        await pilot.press('enter')
        await pilot.pause()
        assert isinstance(app.screen,SurfNftScreen)


async def test_long_filter_caption_is_fitted_and_marks_lost_text():
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen=app.screen
        screen.filters['search']='[/x]界'*100
        screen._repaint_cached()
        await pilot.pause()
        from textual.widgets import Static
        region=screen.query_one('#nft-controls',Static).region
        line=app.screen._compositor.render_strips()[region.y].text
        assert '‹ widen' in line
        assert '[/x]' in line


from maxpane_dashboard.screens.surf_nft import SURF_NFT_FULL_LAYOUT_COLUMNS, SURF_NFT_FULL_LAYOUT_ROWS
from tests.screens._sweeps import boundary_set


@pytest.mark.sweep
@pytest.mark.parametrize('width',boundary_set(SURF_NFT_FULL_LAYOUT_COLUMNS,120,160))
@pytest.mark.parametrize('kind',['normal','empty','unknown'])
async def test_measured_width_boundary_keeps_all_six_frames_and_table_columns(width,kind):
    from textual.containers import VerticalScroll
    from maxpane_dashboard.widgets.surf_nft import NftHero
    app=Harness()
    if kind!='normal':
        app.manager.payload.update(nft_rows=None if kind=='unknown' else [],
                                   nft_build_rows=None if kind=='unknown' else [])
    async with app.run_test(size=(width,45)) as pilot:
        await pilot.pause()
        screen=app.screen; viewport=screen.query_one('#nft-viewport',VerticalScroll)
        hero=screen.query_one(NftHero)
        frames=screen._compositor.render_strips()[hero.region.y].text.count('╮')
        whole=frames==6 and viewport.max_scroll_x==0
        assert whole==(width>=SURF_NFT_FULL_LAYOUT_COLUMNS)
        assert ('‹ widen' in painted(app))==(not whole)
        assert screen.query_one(DataTable).max_scroll_x==0
        if whole:
            assert list(hero.children)[-1].region.right<=viewport.scrollable_content_region.right
            assert all(card.region.height==9 for card in hero.children)
            for label in ('COLLECTION','CHAIN','MINT','IDMD','MINTED/MAX','COLLECTION DETAIL'):
                assert label in painted(app)


@pytest.mark.sweep
@pytest.mark.parametrize('height',boundary_set(SURF_NFT_FULL_LAYOUT_ROWS,24,45))
async def test_measured_height_boundary_keeps_panel_floors_and_scroll_hints(height):
    from textual.containers import VerticalScroll
    app=Harness()
    async with app.run_test(size=(149,height)) as pilot:
        await pilot.pause()
        screen=app.screen; viewport=screen.query_one('#nft-viewport',VerticalScroll)
        whole=viewport.max_scroll_y==0
        assert whole==(height>=SURF_NFT_FULL_LAYOUT_ROWS)
        assert ('‹ taller' in painted(app))==(not whole)
        assert screen.query_one(NftTable).region.height>=18
        assert screen.query_one(NftDetail).region.height>=18
        if whole:
            assert screen.query_one(NftTable).region.bottom<=viewport.region.bottom
            assert 'COLLECTION DETAIL' in painted(app)


async def test_detail_sources_remain_reachable_at_measured_pin():
    app=Harness()
    async with app.run_test(size=(SURF_NFT_FULL_LAYOUT_COLUMNS,SURF_NFT_FULL_LAYOUT_ROWS)) as pilot:
        await pilot.pause()
        detail=app.screen.query_one(NftDetail)
        detail.focus(); detail.scroll_end(animate=False)
        await pilot.pause()
        assert detail.max_scroll_y>0
        assert 'Rule review' in painted(app) and 'Read block' in painted(app)
        assert 'Partial observed coverage' in painted(app)


async def test_contract_search_caption_keeps_copy_and_explicit_chain_link():
    from tests.widgets.address_probe import icon_targets, link_targets
    app=Harness()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        screen=app.screen
        address=app.manager.payload['nft_rows'][0]['contract']
        screen.filters.update(search=address,chain='ethereum')
        screen._repaint_cached()
        await pilot.pause()
        y=screen.query_one('#nft-controls').region.y
        assert any(row==y and target==address for _,row,target in icon_targets(app))
        assert any(row==y and value==address and explorer=='etherscan' for _,row,explorer,_,value,_ in link_targets(app))
