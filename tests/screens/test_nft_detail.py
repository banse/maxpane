"""Cached NFT facts use the shared record popup and retain source actions."""
from copy import deepcopy

import pytest
from textual.app import App
from textual.containers import VerticalScroll

from maxpane_dashboard.screens.nft_detail import NftDetailScreen
from tests.widgets.test_surf_nft import snapshot, painted
from tests.widgets.address_probe import LinkRecorder, icon_targets, link_targets


class Popup(LinkRecorder,App):
    def __init__(self,row):
        super().__init__(); self.row=row
    def on_mount(self):
        self.push_screen(NftDetailScreen(self.row,nft_sources={},nft_coverage={}))


async def all_visible(pilot):
    scroll=pilot.app.screen.query_one(VerticalScroll)
    lines=[]
    for _ in range(100):
        await pilot.pause()
        lines.append(painted(pilot.app))
        if scroll.scroll_y>=scroll.max_scroll_y:
            return '\n'.join(lines)
        scroll.scroll_to(y=min(scroll.scroll_y+max(1,scroll.size.height-1),scroll.max_scroll_y),animate=False)
    raise AssertionError('popup did not reach its final source')


@pytest.mark.parametrize('size',[(149,45),(80,24),(40,12)])
async def test_popup_has_all_extended_sections_and_standard_frame(size):
    row=next(r for r in snapshot()['nft_rows'] if r['name']=='IMDenza')
    async with Popup(row).run_test(size=size) as pilot:
        await pilot.pause()
        screen=pilot.app.screen; scroll=screen.query_one(VerticalScroll)
        assert scroll.has_focus and scroll.max_scroll_x==0
        footer=screen.query_one('#nft-popup-close')
        assert footer.region.bottom<=size[1]-1
        output=await all_visible(pilot)
        for word in ('MINT ROUTES','0.069','Eligibility','UTILITY','RELATED TOKENS','SOURCES · SWARM',
                     'SOURCES · CHAIN & REVIEW','26208001','Partial observed'):
            assert word in output,word
        assert 'PRESS SPACE OR ESC TO CLOSE' in output
        assert 'Supply  minted' not in output


async def test_popup_preserves_exact_source_link_and_unknown_chain_copy_actions():
    row=deepcopy(snapshot()['nft_rows'][0])
    url='https://github.com/identity-md-launches/nft/blob/'+'a'*40+'/src/NFT.sol'
    row.update(chain_id=9999,evidence=[{'label':'Pinned source','url':url}],unknowns=[],rule_review={})
    row['mint']['conditions']='[/x]Requires '+row['contract']
    async with Popup(row).run_test(size=(149,45)) as pilot:
        await pilot.pause()
        assert '[/x]Requires' in painted(pilot.app)
        assert any(value==row['contract'] for _,_,value in icon_targets(pilot.app))
        assert not any(value==row['contract'] for _,_,_,_,value,_ in link_targets(pilot.app))
        pilot.app.screen.query_one(VerticalScroll).scroll_end(animate=False)
        await pilot.pause()
        x,y,*_=next(target for target in link_targets(pilot.app) if target[-1]==url)
        await pilot.click(offset=(x,y))
        assert pilot.app.opened==[url]


@pytest.mark.parametrize('key',['space','escape'])
async def test_popup_close_bindings_return_to_previous_screen(key):
    async with Popup(snapshot()['nft_rows'][0]).run_test(size=(149,45)) as pilot:
        await pilot.pause()
        await pilot.press(key)
        assert not isinstance(pilot.app.screen,NftDetailScreen)
