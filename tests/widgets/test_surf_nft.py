"""NFT primitives render offline evidence without losing identity or links."""
from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.analytics.surf_nft import normalize_record, project_snapshot
from maxpane_dashboard.widgets.surf_nft import NftHero, NftTable, NftDetail, NftSummary


def snapshot():
    raw = json.loads((Path(__file__).parents[1] / 'fixtures/surf/nft/projection.json').read_text())
    rows = [normalize_record(row) for row in raw['records']]
    return dict(nft_rows=[r for r in rows if r['category']=='launched'],
                nft_build_rows=[r for r in rows if r['category']=='in_the_making'],
                nft_summary={'observed_at':raw['observed_at']}, nft_sources={},
                nft_coverage=raw['coverage'], as_of=raw['observed_at'])


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


class Probe(App):
    CSS = '''NftHero {height: 9;} NftTable {height: 18; width: 84;}
    NftDetail {height: 40; width: 74;} NftTable DataTable {height: 1fr;}'''
    def __init__(self, widget):
        super().__init__(); self.widget=widget
    def compose(self):
        yield self.widget


def test_signatures_match_frozen_contract_and_widgets_do_not_import_data():
    from maxpane_dashboard.data.surf_nft_models import NFT_WIDGET_SIGNATURES
    from maxpane_dashboard.widgets.surf_nft import filter as filters
    from maxpane_dashboard.analytics.surf_nft import FILTER_DEFAULTS, FILTER_VALUES
    for cls in (NftHero,NftTable,NftDetail,NftSummary):
        assert tuple(inspect.signature(cls.update_data).parameters)[1:]==NFT_WIDGET_SIGNATURES[cls.__name__]
    assert filters.FILTER_DEFAULTS==FILTER_DEFAULTS
    assert filters.FILTER_VALUES==FILTER_VALUES
    root=Path(__file__).parents[2]/'maxpane_dashboard/widgets/surf_nft'
    for path in root.glob('*.py'):
        assert 'maxpane_dashboard.data' not in path.read_text()


async def test_six_heroes_keep_coverage_state_without_card_footer_notices():
    widget=NftHero()
    async with Probe(widget).run_test(size=(149,45)) as pilot:
        widget.update_data(nft_summary=project_snapshot(snapshot())['nft_summary'])
        await pilot.pause()
        output=painted(pilot.app)
        for title in ('COLLECTIONS','IN THE MAKING','MINT OPEN','IDMD FREE','CONDITIONAL','CHAINS'):
            assert title in output
        assert 'partial' not in output
        assert len(list(widget.children))==6
        for card in widget.children:
            assert card.data.state == 'partial'
            assert 'partial' in str(card.tooltip)
            region=card.region
            footer=pilot.app.screen._compositor.render_strips()[region.bottom-1].crop(region.x,region.right).text
            assert not footer.strip('╰─╯ ')
        widget.update_data(nft_summary=None)
        await pilot.pause()
        assert '--' in painted(pilot.app)
        widget.update_data(nft_summary=dict(deployed=0,building=0,mint_open=0,idmd_free=0,
                                           conditional=0,chains=0,partial=False))
        await pilot.resize_terminal(132,45)
        for card in widget.children:
            assert card.data.digits == '0' and card.data.state == 'ok'
            region=card.region
            footer=pilot.app.screen._compositor.render_strips()[region.bottom-1].crop(region.x,region.right).text
            assert not footer.strip('╰─╯ ')
        widget.update_data(nft_summary=project_snapshot(snapshot())['nft_summary'])
        await pilot.resize_terminal(149,45)
        assert 'partial' not in painted(pilot.app)


async def test_table_keeps_same_name_contracts_and_identity_through_reorder():
    widget=NftTable()
    rows=project_snapshot(snapshot())['nft_rows']
    async with Probe(widget).run_test(size=(149,45)) as pilot:
        widget.update_data(nft_rows=rows, nft_build_rows=[],as_of=1)
        table=widget.query_one(DataTable)
        table.move_cursor(row=2)
        await pilot.pause()
        identity=widget.selected_row()['id']
        widget.update_data(nft_rows=list(reversed(rows)),nft_build_rows=[],as_of=2)
        await pilot.pause()
        assert widget.selected_row()['id']==identity
        assert table.row_count==len(rows)
        assert len([r for r in widget.rows.values() if r['name']=='BMC Illuminati Pass'])==2
        for title in ('COLLECTION','CHAIN','MINT','IDMD','MINTED/MAX'):
            assert title in painted(pilot.app)


async def test_table_site_glyphs_fit_long_names_and_keep_safe_actions_after_reorder():
    from tests.widgets.address_probe import icon_targets, link_targets
    widget=NftTable()
    rows=project_snapshot(snapshot())['nft_rows'][:4]
    for row in rows:
        row['name']='[/x]界'*30
    rows[0]['sites']=[{'label':'bad/label','url':'javascript:alert(1)'},
                      {'label':'first-valid'},{'label':'second-valid'}]
    rows[1].update(chain_id=9999,sites=[{'ensName':'legacy-site.site.identitymd.eth'}])
    rows[2]['sites']=[None,{'label':'bad.label','url':'https://evil.example/'}]
    rows[3]['sites']=[]
    async with Probe(widget).run_test(size=(149,45)) as pilot:
        for values in (rows,list(reversed(rows))):
            widget.update_data(nft_rows=values)
            await pilot.pause()
            links=[target for target in link_targets(pilot.app) if target[2]=='sites']
            assert [target[4] for target in links]==[
                'first-valid' if row['id']==rows[0]['id'] else 'legacy-site'
                for row in values if row['id'] in (rows[0]['id'],rows[1]['id'])]
            for row in values:
                x,y,_=next(target for target in icon_targets(pilot.app) if target[-1]==row['contract'])
                cell=pilot.app.screen._compositor.render_strips()[y].crop(1,24).text
                assert '[/x]' in cell and '…' in cell
                row_links=[target for target in links if target[1]==y]
                if row['id'] in (rows[0]['id'],rows[1]['id']):
                    assert len(row_links)==1 and row_links[0][:2]==(x+2,y)
                    assert cell.endswith('⧉ ↗')
                else:
                    assert not row_links and '↗' not in cell
            assert not any(target[4]==rows[1]['contract'] for target in link_targets(pilot.app))
            assert '‹ widen' not in painted(pilot.app)


async def test_detail_keeps_collection_basics_and_moves_routes_to_popup():
    widget=NftDetail()
    row=next(r for r in snapshot()['nft_rows'] if r['name']=='IMDenza')
    async with Probe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={})
        await pilot.pause()
        output=painted(pilot.app)
        for word in ('IMDenza','3333','Contract','Supply'):
            assert word in output
        assert 'minted' in output and 'live' in output
        assert 'MINT ROUTES' not in output and 'SOURCES' not in output
        assert 'Eligibility' not in output


async def test_literal_hostile_text_and_unknown_chain_have_safe_address_actions():
    from tests.widgets.address_probe import icon_targets, link_targets
    widget=NftDetail()
    row=deepcopy(snapshot()['nft_rows'][0])
    row.update(name='[/x]恶意\x1bname',chain_id=9999)
    row['mint']['conditions']='Requires '+row['contract']
    row['sites']=[{'label':'unsafe','url':'javascript:alert(1)'}]
    async with Probe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={})
        await pilot.pause()
        assert '[/x]恶意name' in painted(pilot.app)
        assert row['contract'].lower() in {target.lower() for _,_,target in icon_targets(pilot.app) if target}
        assert not any('javascript:' in str(value) for value in link_targets(pilot.app))
        assert not any(row['contract'].lower() in str(value).lower() for value in link_targets(pilot.app))


@pytest.mark.parametrize('url',['javascript:alert(1)','file:///etc/passwd','https://user:secret@example.com',
                                'https://example.com\n/redirect','https://example.com\\@evil.test',
                                'https://localhost/path'])
def test_source_url_rejects_non_public_or_executable_links(url):
    from maxpane_dashboard.widgets.surf_nft.detail import source_url
    assert source_url(url) is None


async def test_farm_supply_distinguishes_burns_and_two_holder_definitions():
    row=next(r for r in snapshot()['nft_rows'] if r['name']=='FarmItems')
    widget=NftDetail()
    async with Probe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={})
        await pilot.pause()
        output=painted(pilot.app)
        for value in ('minted 114','live 110','Burned  4','Custody holders  9','Beneficial holders  11'):
            assert value in output


async def test_summary_is_literal_scrollable_and_keeps_unknown_chain_addresses_copyable():
    from tests.widgets.address_probe import icon_targets, link_targets
    from maxpane_dashboard.widgets.address import is_address
    widget=NftSummary()
    address='0x'+'a'*40
    readme=dict(identity='project:one',repository_url='https://github.com/example/nft',
                readme_url='https://github.com/example/nft/blob/main/README.md',revision='main',
                text='[/x]README\x1b text '+address+'\n'+'Long public excerpt.\n'*100,
                observed_at=123,state='ok')
    async with Probe(widget).run_test(size=(90,25)) as pilot:
        widget.update_data(nft_readme=readme)
        await pilot.pause()
        assert 'SUMMARY (github README.md)' in painted(pilot.app)
        assert '[/x]README text' in painted(pilot.app)
        assert any(value==address for _,_,value in icon_targets(pilot.app))
        assert not any(is_address(value) for _,_,_,_,value,_ in link_targets(pilot.app))
        assert widget.max_scroll_y>0
        widget.update_data(nft_readme=None)
        await pilot.pause()
        assert '[/x]README' not in painted(pilot.app)
        assert 'unavailable' not in painted(pilot.app) and 'stale' not in painted(pilot.app)


async def test_summary_source_click_uses_the_exact_readme_url():
    from tests.widgets.address_probe import LinkRecorder, link_targets
    class LinkedProbe(LinkRecorder,Probe): pass
    widget=NftSummary()
    url='https://github.com/example/nft/blob/'+'a'*40+'/README.md'
    async with LinkedProbe(widget).run_test(size=(90,25)) as pilot:
        widget.update_data(nft_readme=dict(identity='one',repository_url='https://github.com/example/nft',
            readme_url=url,text='Excerpt from this pinned README'))
        await pilot.pause()
        x,y,*_=next(target for target in link_targets(pilot.app) if target[-1]==url)
        await pilot.click(offset=(x,y))
        assert pilot.app.opened==[url]
