"""NFT primitives render offline evidence without losing identity or links."""
from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.analytics.surf_nft import normalize_record, project_snapshot
from maxpane_dashboard.widgets.surf_nft import NftHero, NftTable, NftDetail


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
    for cls in (NftHero,NftTable,NftDetail):
        assert tuple(inspect.signature(cls.update_data).parameters)[1:]==NFT_WIDGET_SIGNATURES[cls.__name__]
    assert filters.FILTER_DEFAULTS==FILTER_DEFAULTS
    assert filters.FILTER_VALUES==FILTER_VALUES
    root=Path(__file__).parents[2]/'maxpane_dashboard/widgets/surf_nft'
    for path in root.glob('*.py'):
        assert 'maxpane_dashboard.data' not in path.read_text()


async def test_six_heroes_use_observed_counts_and_explicit_partial_coverage():
    widget=NftHero()
    async with Probe(widget).run_test(size=(149,45)) as pilot:
        widget.update_data(nft_summary=project_snapshot(snapshot())['nft_summary'])
        await pilot.pause()
        output=painted(pilot.app)
        for title in ('COLLECTIONS','IN THE MAKING','MINT OPEN','IDMD FREE','CONDITIONAL','CHAINS'):
            assert title in output
        assert output.count('partial')==6
        assert len(list(widget.children))==6
        widget.update_data(nft_summary=None)
        await pilot.pause()
        assert '--' in painted(pilot.app)


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


async def test_detail_displays_independent_routes_supply_and_eligibility():
    widget=NftDetail()
    row=next(r for r in snapshot()['nft_rows'] if r['name']=='IMDenza')
    async with Probe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={})
        await pilot.pause()
        output=painted(pilot.app)
        for word in ('IMDenza','0.069','IDMD','3333','Eligibility','not checked','MINT ROUTES'):
            assert word in output
        assert 'minted' in output and 'live' in output
        widget.scroll_end(animate=False)
        await pilot.pause()
        output=painted(pilot.app)
        assert 'SOURCE' in output and '26208001' in output
        assert widget.max_scroll_y>0


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


async def test_source_link_click_opens_the_exact_validated_source():
    from tests.widgets.address_probe import LinkRecorder, link_targets
    class LinkedProbe(LinkRecorder,Probe):
        pass
    widget=NftDetail()
    row=deepcopy(snapshot()['nft_rows'][0])
    url='https://github.com/identity-md-launches/nft/blob/'+'a'*40+'/src/NFT.sol'
    row.update(evidence=[{'label':'Pinned source','url':url}],unknowns=[],rule_review={})
    async with LinkedProbe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={'complete':True})
        widget.scroll_end(animate=False)
        await pilot.pause()
        x,y,*_=next(target for target in link_targets(pilot.app) if target[-1]==url)
        await pilot.click(offset=(x,y))
        assert pilot.app.opened==[url]


async def test_farm_supply_distinguishes_burns_and_two_holder_definitions():
    row=next(r for r in snapshot()['nft_rows'] if r['name']=='FarmItems')
    widget=NftDetail()
    async with Probe(widget).run_test(size=(149,50)) as pilot:
        widget.update_data(nft_selected=row,nft_sources={},nft_coverage={})
        await pilot.pause()
        output=painted(pilot.app)
        for value in ('minted 114','live 110','Burned  4','Custody holders  9','Beneficial holders  11'):
            assert value in output
