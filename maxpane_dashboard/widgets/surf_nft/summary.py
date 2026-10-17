"""Literal cached README excerpt; repository prose never assumes an address chain."""
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_prose
from maxpane_dashboard.widgets.panels import PanelBase
from .detail import source_text, source_url


class _SummaryBody(Static):
    def action_open_source(self,index):
        self.parent.action_open_source(index)


class NftSummary(PanelBase,can_focus=True):
    TITLE='SUMMARY (github README.md)'
    BINDINGS=VerticalScroll.BINDINGS
    DEFAULT_CSS='''
    NftSummary {height: 1fr; min-height: 8; overflow-y: auto; scrollbar-gutter: stable; scrollbar-size: 1 1;}
    NftSummary #nft-summary-body {height: auto; padding: 0 1; link-color: $foreground;}
    NftSummary:focus {background: $background;}
    '''

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self._identity=None; self._links=[]

    def compose_body(self):
        yield _SummaryBody(Text('—'),id='nft-summary-body')

    def action_open_source(self,index):
        if type(index) is int and 0<=index<len(self._links):
            url=source_url(self._links[index])
            if url:
                self.app.open_url(url)

    def update_data(self,*,nft_readme=None):
        data=nft_readme if isinstance(nft_readme,dict) else {}
        if self._identity!=data.get('identity'):
            self.scroll_home(animate=False)
        self._identity=data.get('identity'); self._links=[]
        out=Text()
        if data.get('repository_url'):
            out.append_text(source_text(data['repository_url'],data.get('readme_url') or data['repository_url'],self._links))
            out.append('\n\n')
        out.append_text(address_prose(data.get('text') or '—',explorer=None))
        self.write('#nft-summary-body',out)
