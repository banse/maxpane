"""Retained NFT Explorer; controls project cached facts without offering reads."""
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Input, Select, Static

from maxpane_dashboard.analytics.surf_nft import FILTER_DEFAULTS, project_snapshot
from maxpane_dashboard.screens.dashboard_screen import keys
from maxpane_dashboard.screens.nft_detail import NftDetailScreen
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import cell_len
from maxpane_dashboard.widgets.surfboard.terminal import fit_prose
from maxpane_dashboard.widgets.surf_nft import NftHero, NftTable, NftDetail, NftSummary, EXPLORER
from maxpane_dashboard.widgets.surf_nft.filter import NftFilterEditor


#: Measured 2026-10-19 after the owner-visible keyless Matrix 149×45 preview.
#: The controls occupy the previously unused top row above six rack heroes.
#: Hero tops remain at row 1; table and basics start at row 11 instead of 13.
#: Removing the old controls slot and spacer recovers two panel rows.
#: The list keeps a fixed width; basics and README summary share the right column.
#: Basic facts and README prose scroll independently inside their panels.
#: At 149×45 the complete list and detail headers are visible together.
#: All six hero frames remain on one row; each is nine rows high.
#: The measurement used the production stylesheet and actual screen containers.
#: Width samples began at 120 columns and extended to 160, independently of
#: this constant; near the transition every column from 140 to 149 was read.
#: At 145 columns the reserved viewport gutter clips the rightmost frame.
#: Its horizontal scroll extent is one column; generated widen hints are hidden
#: everywhere in this view by owner request. Geometry remains the width signal.
#: At 146 columns all six right corners are visible and no outer scroll remains.
#: At 147 and 149 columns the complete frames and both panels stay visible.
#: The table's five installed columns fit without internal horizontal scrolling;
#: its row-end popup action uses two cells from the existing final column.
#: Name windows retain copy icons and the full identity stays in the detail.
#: A linked site's one-cell glyph and spacer use two cells of the name window;
#: its shared validated explorer action follows the copy icon without widening.
#: Source text may still wrap or scroll; the pin is not a promise about text length.
#: Height samples began at 24 rows and extended through 45 rows.
#: At 30 rows the body exceeds the viewport by one row and marks taller.
#: At 31 rows the body, table floor and status bar fit without outer scrolling.
#: At 32 rows the extra row goes to the independently scrolling summary/list.
#: The fixed body floor is 29 rows; header and status bar remain outside it.
#: Normal, unread and confirmed-empty payloads share these geometry boundaries.
#: Basics are capped at half the column so extra holder/project facts cannot
#: push the summary below the column. Its eight-row floor stays wholly visible.
#: The ordinary fixture has nine-row basics and a nine-row summary at the pin.
#: A longer basics fixture scrolls internally while the outer viewport stays whole.
#: Extended mint/source evidence now uses the independently scrolling RECORD modal.
#: The live NFT catalogue and Boardroom were shown at 149×45 before this sweep.
#: Boardroom's NFT card moves build/open counts to its outer footer.
#: Neither the hub's 143×37 pin nor the application width changes here.
#: Boundary tests exercise both sides of each measured onset and inspect frames,
#: table columns and viewport extents rather than trusting a marker alone.
#: Pin mutations in either direction must change the expected boundary result.
SURF_NFT_FULL_LAYOUT_COLUMNS = 146
SURF_NFT_FULL_LAYOUT_ROWS = 31


class SurfNftScreen(SurfDashboardScreen):
    GAME_NAME='NFT EXPLORER'
    JOIN_STARTUP_PREFETCH=False
    REFRESH_WORKER_NAME='surf-nft-refresh'
    PANELS=((NftHero,keys('nft_summary')),
            (NftTable,keys('nft_rows','nft_build_rows','as_of')),
            (NftDetail,keys('nft_selected','nft_sources','nft_coverage')),
            (NftSummary,keys('nft_readme')))
    BINDINGS=[Binding('escape','back',show=False),Binding('f','filter',show=False),
              Binding('/','search',show=False),Binding('b','stage',show=False),
              Binding('c','chain',show=False),Binding('o','sort',show=False)]
    DEFAULT_CSS='''
    SurfNftScreen {background: $background; color: $text;}
    SurfNftScreen #nft-viewport {height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1;}
    SurfNftScreen #nft-body {width: 1fr; min-width: 143; height: 1fr; min-height: 29;}
    SurfNftScreen NftHero {height: 9; margin: 0 0 1 0;}
    SurfNftScreen #nft-controls {height: 1; padding: 0 2;}
    SurfNftScreen #nft-content {height: 1fr; min-height: 18;}
    SurfNftScreen #nft-market {height: 1fr;}
    SurfNftScreen NftTable {width: 77; height: 1fr; min-height: 18; margin-right: 1; border: none;}
    SurfNftScreen #nft-inspection {width: 1fr; height: 1fr; min-height: 18;}
    SurfNftScreen NftDetail {height: auto; min-height: 7; max-height: 50%; margin-bottom: 1; border: none;}
    SurfNftScreen NftSummary {height: 1fr; min-height: 8; border: none;}
    SurfNftScreen DataTable {height: 1fr; background: $background; scrollbar-size: 1 1;}
    SurfNftScreen .panel-title {height: 1; padding: 0 1; margin-bottom: 1;
        color: $text-muted; text-wrap: nowrap; text-overflow: ellipsis;}
    SurfNftScreen NftFilterEditor {display: none;}
    '''

    def __init__(self,manager,poll_interval=30,name='surf-nft',*,view_state=None,**kwargs):
        super().__init__(manager,poll_interval,name=name,**kwargs)
        self._view_state=view_state if isinstance(view_state,dict) else {}
        self.filters=dict(self._view_state.get('filters') or FILTER_DEFAULTS); self.snapshot={}; self._raw={}
        self._selected_id=self._view_state.get('selected_id'); self._filter_open=False
        self._readme=None

    def compose(self):
        yield Static(Text('NFT EXPLORER'),id='nft-controls')
        with VerticalScroll(id='nft-viewport'):
            with Vertical(id='nft-body'):
                yield NftHero()
                with Vertical(id='nft-content'):
                    with Horizontal(id='nft-market'):
                        yield NftTable()
                        with Vertical(id='nft-inspection'):
                            yield NftDetail()
                            yield NftSummary()
                    yield NftFilterEditor()
        yield SurfStatusBar()

    def on_mount(self):
        self.call_after_refresh(lambda:self.query_one(DataTable).focus())

    def _prime_status_bar(self,bar):
        bar.set_key_hints('f filter · / find · b stage · c chain · o sort · enter detail · tab · esc back')

    async def _fetch_data(self):
        self._raw=await super()._fetch_data()
        return self._project()

    def _project(self):
        self.query_one(NftTable).stage=self.filters['stage']
        data=project_snapshot(self._raw,filters=self.filters,selected_id=self._selected_id)
        selected=data.get('nft_selected')
        if selected:
            self._selected_id=selected['id']
        return data

    def _update_title(self,data):
        self._view_state.update(filters=dict(self.filters),selected_id=self._selected_id)
        self.snapshot=data
        selected=data.get('nft_selected')
        self._data_manager.select(selected['id'] if selected else None)
        data['nft_readme']=self._readme=self._selected_readme(allow_snapshot=True)
        if selected:
            self.call_after_refresh(self.query_one(NftTable).select_identity,selected['id'])
        self.call_after_refresh(self._chrome)

    def _selected_readme(self,*,allow_snapshot=False):
        getter=getattr(self._data_manager,'get_readme',None)
        data=getter() if callable(getter) else (
            self._data_manager.get_snapshot().get('nft_readme') if allow_snapshot else None)
        selected=self.snapshot.get('nft_selected') or {}
        return data if selected and isinstance(data,dict) and data.get('identity')==selected.get('id') else None

    def _tick_loading(self):
        super()._tick_loading()
        if self.is_current and callable(getattr(self._data_manager,'get_readme',None)):
            data=self._selected_readme()
            if data!=self._readme:
                self.snapshot['nft_readme']=self._readme=data
                self.query_one(NftSummary).update_data(nft_readme=data)

    def _repaint_cached(self):
        self._raw=self._data_manager.get_snapshot() or {}
        data=self._project()
        self._update_title(data)
        for widget,adapt in self.PANELS:
            self.query_one(widget).update_data(**adapt(data))

    def on_resize(self):
        self.call_after_refresh(self._chrome)

    def _chrome(self):
        viewport=self.query_one('#nft-viewport',VerticalScroll)
        editor=self.query_one(NftFilterEditor)
        editor.styles.width=viewport.scrollable_content_region.width
        suffix=' · ‹ taller' if viewport.max_scroll_y>0 else ''
        chain={'all':'all chains','ethereum':'Ethereum','robinhood':'Robinhood'}[self.filters['chain']]
        selection=' · '.join(f'{key}: {flatten(value)}' for key,value in self.filters.items()
            if key in ('idmd','mint','utility','search') and value not in ('all',''))
        stage='LAUNCHED' if self.filters['stage']=='launched' else 'IN THE MAKING'
        text=f'NFT EXPLORER{self.loading_suffix} · {stage} · {chain}'
        if selection:
            text+=' · '+selection
        if (self.snapshot.get('nft_coverage') or {}).get('complete') is not True:
            text+=' · partial catalogue'
        control=self.query_one('#nft-controls',Static)
        room=max(1,control.content_size.width)
        explorer=EXPLORER({'ethereum':1,'robinhood':4663}.get(self.filters['chain']))
        caption,_=fit_prose(text,max(1,room-cell_len(suffix)),explorer=explorer)
        control.update(caption.append(suffix))

    def on_nft_table_highlighted(self,event):
        event.stop()
        if event.row:
            self._selected_id=event.row['id']
            self._view_state['selected_id']=self._selected_id
            self._data_manager.select(self._selected_id)
            self.snapshot['nft_selected']=event.row
            self.snapshot['nft_readme']=self._readme=self._selected_readme(allow_snapshot=True)
            self.query_one(NftSummary).update_data(nft_readme=self._readme)
            self.query_one(NftDetail).update_data(nft_selected=event.row,
                nft_sources=self.snapshot.get('nft_sources'),nft_coverage=self.snapshot.get('nft_coverage'))

    def on_nft_table_selected(self,event):
        event.stop()
        if event.row:
            self.app.push_screen(NftDetailScreen(event.row,nft_sources=self.snapshot.get('nft_sources'),
                                                 nft_coverage=self.snapshot.get('nft_coverage')))

    def action_open_nft_detail(self,index):
        rows=list(self.query_one(NftTable).rows.values())
        if type(index) is int and 0<=index<len(rows):
            self.on_nft_table_selected(NftTable.Selected(rows[index]))

    def _show_filter(self,show):
        self._filter_open=show
        self.query_one('#nft-market').display=not show
        self.query_one(NftFilterEditor).display=show
        bar=self.query_one(SurfStatusBar)
        if show:
            bar.set_key_hints('f apply · esc cancel · tab fields · APPLY FILTER / RESET ALL')
        else:
            self._prime_status_bar(bar)
        self.call_after_refresh(self._chrome)

    def action_filter(self):
        if isinstance(self.focused,Input):
            return
        if self._filter_open:
            self._apply_filter(); return
        editor=self.query_one(NftFilterEditor)
        rows=(self._raw.get('nft_rows') or [])+(self._raw.get('nft_build_rows') or [])
        editor.set_utilities(item.get('kind') for row in rows for item in row.get('utility') or [] if isinstance(item,dict))
        editor.set_values(self.filters)
        self._show_filter(True)
        self.call_after_refresh(lambda:editor.query_one(Select).focus())

    def _apply_filter(self):
        self.filters=self.query_one(NftFilterEditor).values()
        self.filters['search']=self.filters['search'].strip()
        self._show_filter(False); self._repaint_cached()
        self.call_after_refresh(lambda:self.query_one(DataTable).focus())

    def on_nft_filter_apply_requested(self,event):
        event.stop()
        if self._filter_open:
            self._apply_filter()

    def on_nft_filter_reset_requested(self,event):
        event.stop(); self.query_one(NftFilterEditor).set_values(FILTER_DEFAULTS)

    def action_search(self):
        if not self._filter_open:
            self.action_filter()
        self.call_after_refresh(lambda:self.query_one('#filter-search',Input).focus())

    def action_stage(self):
        if not self._filter_open:
            self.filters['stage']='building' if self.filters['stage']=='launched' else 'launched'
            self._repaint_cached()

    def action_chain(self):
        if not self._filter_open:
            choices=['all','ethereum','robinhood']
            self.filters['chain']=choices[(choices.index(self.filters['chain'])+1)%len(choices)]
            self._repaint_cached()

    def action_sort(self):
        if not self._filter_open:
            self.filters['sort']='name' if self.filters['sort']=='newest' else 'newest'
            self._repaint_cached()

    def action_back(self):
        if self._filter_open:
            self._show_filter(False)
            self.call_after_refresh(lambda:self.query_one(DataTable).focus())
        else:
            self.app.pop_screen()
