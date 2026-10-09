"""Approved market overview, with an explicitly offline demo data provider."""
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Input, Select, Static

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.swarm_tokens import (
    BestPlays, NewlyLaunched, TokenActivity, TokensHero, TokensTable,
)
from maxpane_dashboard.widgets.swarm_tokens.detail import SwarmTokenDetail
from maxpane_dashboard.widgets.swarm_tokens.filter import SwarmTokensFilterEditor

#: Mock overview measured in the real screen after its 149x45 preview.
#: Native revision: at 145x35 all thirteen table columns, four heroes and
#: three lower panels fit without an outer scrollbar. At 144x35 or 145x34
#: the viewport scrolls and advertises the reduced space. At 149x45 the
#: table shows seventeen data rows, with the remaining rows behind its scrollbar.
#: The table keeps all 24 rows and scrolls internally at every measured size.
#: Widgets retain a 143-column body and 33-row content floor; a vertical
#: scrollbar below the row pin can also require a horizontal one.
SWARM_TOKENS_FULL_LAYOUT_COLUMNS = 145
SWARM_TOKENS_FULL_LAYOUT_ROWS = 35


class DemoStatusBar(StatusBar):
    """The demo has a frozen snapshot, so never imply a fresh market read."""
    def _ordinary_status(self, *_args):
        return self._key_hints or 'q quit · r refresh · m/esc back · tab panels · f filter · / find · c chain · o sort · enter details'


class SwarmTokensScreen(DashboardScreen):
    GAME_NAME = 'SWARM TOKENS · MOCK'
    REFRESH_WORKER_NAME = 'swarm-tokens-demo-refresh'
    # This provider is offline and independent of the application's live prefetch.
    JOIN_STARTUP_PREFETCH = False
    PANELS = (
        (TokensHero, keys('metrics')),
        (TokensTable, keys('tokens', 'as_of')),
        (NewlyLaunched, keys('newly_launched', 'as_of')),
        (BestPlays, keys('gainers', 'losers')),
        (TokenActivity, keys('activity', 'tokens')),
    )
    BINDINGS = [
        Binding('escape', 'back', show=False), Binding('m', 'back', show=False),
        Binding('/', 'search', show=False), Binding('c', 'chain', show=False),
        Binding('o', 'sort', show=False),
        Binding('f', 'filter', show=False),
    ]
    DEFAULT_CSS = '''
    SwarmTokensScreen { background: $background; color: $text; }
    SwarmTokensScreen #st-title { height: 1; margin-bottom: 1; padding: 0 1; color: $text-muted;
        text-wrap: nowrap; text-overflow: ellipsis; }
    SwarmTokensScreen #st-viewport { height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-body { width: 1fr; min-width: 143; height: 1fr; min-height: 33; }
    SwarmTokensScreen TokensHero { height: 7; margin: 1 0; }
    SwarmTokensScreen TokensHeroBox { width: 1fr; height: 7; border: solid $panel;
        background: $surface; padding: 0 1; margin: 0 1; content-align: center middle;
        text-align: center; }
    SwarmTokensScreen #st-content { height: 1fr; min-height: 22; }
    SwarmTokensScreen #st-market { height: 1fr; }
    SwarmTokensScreen TokensTable { height: 1fr; min-height: 10; border: none; }
    SwarmTokensScreen DataTable { height: 1fr; background: $background; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-bottom { height: 11; margin-top: 1; }
    SwarmTokensScreen NewlyLaunched, SwarmTokensScreen BestPlays, SwarmTokensScreen TokenActivity {
        width: 1fr; height: 1fr; border: none; }
    SwarmTokensScreen NewlyLaunched, SwarmTokensScreen BestPlays { margin-right: 1; }
    SwarmTokensScreen .panel-title { height: 1; padding: 0 1; margin-bottom: 1; color: $text-muted; }
    SwarmTokensScreen RichLog { height: 1fr; padding: 0 1; background: $background;
        scrollbar-size: 1 1; }
    SwarmTokensScreen #st-best-body { height: 1fr; padding: 0 1; }
    SwarmTokensScreen SwarmTokensFilterEditor { display: none; }
    SwarmTokensScreen #st-selection { height: 1; color: $text-muted; padding: 0 1;
        text-wrap: nowrap; text-overflow: ellipsis; }
    '''

    def __init__(self, manager, poll_interval=30, name='swarm-tokens-demo', *, standalone=False, **kwargs):
        super().__init__(manager, poll_interval, name=name, **kwargs)
        self.snapshot = {}
        self.chain = 'all'
        self.search_query = ''
        self.lp_state = 'all'
        self.sort = 'volume'
        self._standalone = standalone
        self._filter_open = False

    def compose(self):
        with VerticalScroll(id='st-viewport'):
            with Vertical(id='st-body'):
                yield TokensHero()
                yield Static(Text('SWARM TOKENS · MOCK DATA'), id='st-title')
                with Vertical(id='st-content'):
                    with Vertical(id='st-market'):
                        yield TokensTable()
                        with Horizontal(id='st-bottom'):
                            yield NewlyLaunched()
                            yield BestPlays()
                            yield TokenActivity()
                    yield SwarmTokensFilterEditor()
        yield Static(Text('Select a token · Enter for details'), id='st-selection')
        yield DemoStatusBar()

    async def _fetch_data(self):
        raw = await self._data_manager.fetch_and_compute()
        return project_snapshot(raw, chain=self.chain, query=self.search_query,
                                lp_state=self.lp_state, sort=self.sort)

    def _update_title(self, data):
        self.snapshot = data
        self.call_after_refresh(self._chrome)

    def on_mount(self):
        self.call_after_refresh(lambda: self.query_one(TokensTable).query_one('DataTable').focus())

    def on_resize(self):
        self.call_after_refresh(self._chrome)

    def _chrome(self):
        viewport = self.query_one('#st-viewport',VerticalScroll)
        # Keep the native editor within the visible viewport even when the
        # market's wider hero/table canvas needs horizontal scrolling.
        editor=self.query_one(SwarmTokensFilterEditor)
        editor.styles.width=viewport.scrollable_content_region.width
        if self._filter_open:
            # Revealing from a horizontally scrolled canvas can settle the
            # width after Resize was delivered. Reuse the base's compact rule
            # once the visible editor has its final content geometry.
            self.call_after_refresh(editor.on_resize)
        suffix = (' · ‹ widen' if viewport.show_horizontal_scrollbar else '')
        suffix += ' · ‹ taller' if viewport.show_vertical_scrollbar else ''
        chain={'all':'all chains','eth':'Ethereum','base':'Base','rh':'Robinhood'}[self.chain]
        state='FILTER · draft' if self._filter_open else chain
        selection=f' · {self.lp_state}' if self.lp_state!='all' else ''
        selection+=f' · search: {flatten(self.search_query)}' if self.search_query else ''
        self.query_one('#st-title',Static).update(Text(
            f'SWARM TOKENS · MOCK DATA{suffix} · {state}{selection} · sort: {self.sort}', style='bold'))
        self._selection(self.query_one(TokensTable).selected_token())

    def _show_filter(self, editing):
        self._filter_open=editing
        self.query_one('#st-market').display=not editing
        self.query_one(SwarmTokensFilterEditor).display=editing
        self.query_one(DemoStatusBar).set_key_hints(
            'f apply · esc cancel · tab fields · APPLY FILTER / RESET ALL' if editing else '')
        self.call_after_refresh(self._chrome)

    def action_filter(self):
        if self._filter_open:
            self._apply_filter()
            return
        editor=self.query_one(SwarmTokensFilterEditor)
        editor.set_values(dict(chain='any' if self.chain=='all' else self.chain,
                               liquidity='any' if self.lp_state=='all' else self.lp_state,
                               sort='any' if self.sort=='volume' else self.sort,
                               query=self.search_query))
        self._show_filter(True)
        self.call_after_refresh(lambda: editor.query_one(Select).focus())

    def _apply_filter(self):
        values=self.query_one(SwarmTokensFilterEditor).values()
        self.chain='all' if values['chain']=='any' else values['chain']
        self.lp_state='all' if values['liquidity']=='any' else values['liquidity']
        self.sort='volume' if values['sort']=='any' else values['sort']
        self.search_query=values['query'].strip()
        self._show_filter(False)
        self.action_refresh()
        self.call_after_refresh(lambda: self.query_one(DataTable).focus())

    def on_swarm_tokens_filter_apply_requested(self,event):
        event.stop()
        if self._filter_open:
            self._apply_filter()

    def on_swarm_tokens_filter_reset_requested(self,event):
        event.stop()
        self.query_one(SwarmTokensFilterEditor).set_values({})

    def on_tokens_table_highlighted(self,event):
        self._selection(event.token)

    def _selection(self,token):
        if not token:
            text='No token selected'
        else:
            text=(f"{token.get('symbol')} / {token.get('chain','').upper()} / #{token.get('launch_id')}"
                  f" · {token.get('name')} · LP: {token.get('lp_state')} · Enter for mock details")
        self.query_one('#st-selection',Static).update(Text(flatten(text)))

    def on_tokens_table_selected(self,event):
        event.stop()
        if event.token:
            self.app.push_screen(SwarmTokenDetail(event.token))

    def action_search(self):
        if not self._filter_open:
            self.action_filter()
        self.call_after_refresh(lambda: self.query_one('#filter-query',Input).focus())

    def action_chain(self):
        if self._filter_open:
            return
        values=['all','eth','base','rh']
        self.chain=values[(values.index(self.chain)+1)%len(values)]
        self.action_refresh()

    def action_sort(self):
        if self._filter_open:
            return
        values=['volume','change','newest','symbol']
        self.sort=values[(values.index(self.sort)+1)%len(values)]
        self.action_refresh()

    def action_back(self):
        if self._filter_open:
            self._show_filter(False)
            self.call_after_refresh(lambda: self.query_one(DataTable).focus())
        elif self._standalone:
            self.app.exit()
        else:
            self.app.pop_screen()
