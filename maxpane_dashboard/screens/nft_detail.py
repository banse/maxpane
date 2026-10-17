"""NFT mint routes, utility and source evidence from the exact cached table row."""
from copy import deepcopy

from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.surf_nft import EXPLORER
from maxpane_dashboard.widgets.surf_nft.detail import render_detail, source_url
from maxpane_dashboard.widgets.surfboard.terminal import fit_prose


class NftDetailScreen(RecordDetailScreen):
    ID_PREFIX='nft-popup'

    def __init__(self,row,*,nft_sources=None,nft_coverage=None):
        super().__init__(row)
        self._sources=deepcopy(nft_sources); self._coverage=deepcopy(nft_coverage)
        self._links=[]

    def compose_sections(self):
        content,self._links=render_detail(self.row,nft_sources=self._sources,
                                          nft_coverage=self._coverage,extended=True)
        yield Static(content)

    def _title(self):
        title=self.query_one('.record-detail-title',Static)
        name=self.row.get('name') or self.row.get('symbol') or 'Unnamed collection'
        text,_=fit_prose('NFT · '+str(name),max(1,title.size.width),explorer=EXPLORER(self.row.get('chain_id')))
        title.update(text)

    def action_open_source(self,index):
        if type(index) is int and 0<=index<len(self._links):
            url=source_url(self._links[index])
            if url:
                self.app.open_url(url)
