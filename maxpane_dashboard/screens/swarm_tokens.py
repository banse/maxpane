"""Approved market overview, with an explicitly offline demo data provider."""
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Select, Static

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.swarm_tokens import (
    BestPlays, NewlyLaunched, TokenActivity, TokensHero, TokensTable,
)
from maxpane_dashboard.widgets.swarm_tokens.detail import SwarmTokenDetail

#: Mock overview measured in the real screen after its 149x45 preview.
#: At 145x40 all thirteen table columns, four heroes and three lower panels
#: fit without an outer scrollbar. At 144x40 the viewport scrolls horizontally;
#: at 145x39 it scrolls vertically and advertises the reduced space.
#: The table keeps all 24 rows and scrolls internally at every measured size.
#: Widgets retain a 143-column body and 37-row content floor; a vertical
#: scrollbar below the row pin can also require a horizontal one.
SWARM_TOKENS_FULL_LAYOUT_COLUMNS = 145
SWARM_TOKENS_FULL_LAYOUT_ROWS = 40


class DemoStatusBar(StatusBar):
    """The demo has a frozen snapshot, so never imply a fresh market read."""
    def _ordinary_status(self, *_args):
        return 'q quit · r refresh · m/esc back · tab panels · / find · c chain · o sort · enter details'


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
    ]
    DEFAULT_CSS = '''
    SwarmTokensScreen { background: $background; color: $text; }
    SwarmTokensScreen #st-title { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    SwarmTokensScreen #st-viewport { height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-body { width: 1fr; min-width: 143; height: 1fr; min-height: 37; }
    SwarmTokensScreen #st-controls { height: 3; margin: 1 0 0 0; }
    SwarmTokensScreen Select { width: 24; height: 3; margin-right: 1; }
    SwarmTokensScreen #st-search { width: 1fr; height: 3; }
    SwarmTokensScreen TokensHero { height: 6; margin: 1 0; }
    SwarmTokensScreen TokensHeroBox { width: 1fr; height: 6; border: round $panel;
        background: $surface; padding: 0 1; margin-right: 1; content-align: center middle;
        text-align: center; }
    SwarmTokensScreen TokensHeroBox:last-child { margin-right: 0; }
    SwarmTokensScreen TokensTable { height: 1fr; min-height: 12; border: solid $panel; }
    SwarmTokensScreen DataTable { height: 1fr; background: $background; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-bottom { height: 12; margin-top: 1; }
    SwarmTokensScreen NewlyLaunched, SwarmTokensScreen BestPlays, SwarmTokensScreen TokenActivity {
        width: 1fr; height: 1fr; border: solid $panel; }
    SwarmTokensScreen NewlyLaunched, SwarmTokensScreen BestPlays { margin-right: 1; }
    SwarmTokensScreen .panel-title { height: 1; padding: 0 1; margin-bottom: 1; color: $text-muted; }
    SwarmTokensScreen RichLog { height: 1fr; padding: 0 1; background: $background;
        scrollbar-size: 1 1; }
    SwarmTokensScreen #st-best-body { height: 1fr; padding: 0 1; }
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

    def compose(self):
        yield Static(Text('SURFBOARD / SWARM TOKENS · MOCK DATA'), id='st-title')
        with VerticalScroll(id='st-viewport'):
            with Vertical(id='st-body'):
                with Horizontal(id='st-controls'):
                    yield Select([('All chains','all'),('Ethereum','eth'),('Base','base'),('Robinhood','rh')],
                                 value='all', allow_blank=False, id='st-chain')
                    yield Select([('All liquidity','all'),('Two-sided','two-sided'),('One-sided','one-sided'),
                                  ('Withdrawn / unknown','issues')], value='all', allow_blank=False, id='st-lp')
                    yield Select([('Volume ↓','volume'),('24h change ↓','change'),('Newest first','newest'),
                                  ('Token A–Z','symbol')], value='volume', allow_blank=False, id='st-sort')
                    yield Input(placeholder='Search token, name or launch #', id='st-search')
                yield TokensHero()
                yield TokensTable()
                with Horizontal(id='st-bottom'):
                    yield NewlyLaunched()
                    yield BestPlays()
                    yield TokenActivity()
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
        suffix = (' · ‹ widen' if viewport.show_horizontal_scrollbar else '')
        suffix += ' · ‹ taller' if viewport.show_vertical_scrollbar else ''
        total = (self.snapshot.get('metrics') or {}).get('total',0)
        self.query_one('#st-title',Static).update(Text(
            f'SURFBOARD / SWARM TOKENS · MOCK DATA · {total} tokens · 24h window{suffix}', style='bold'))
        self._selection(self.query_one(TokensTable).selected_token())

    @on(Select.Changed)
    def filters_changed(self,event):
        attribute={'st-chain':'chain','st-lp':'lp_state','st-sort':'sort'}.get(event.select.id)
        if attribute and isinstance(event.value,str):
            setattr(self,attribute,event.value)
            self.action_refresh()

    @on(Input.Changed,'#st-search')
    def search_changed(self,event):
        self.search_query=event.value
        self.action_refresh()

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
        self.query_one('#st-search',Input).focus()

    def action_chain(self):
        values=['all','eth','base','rh']
        self.query_one('#st-chain',Select).value=values[(values.index(self.chain)+1)%len(values)]

    def action_sort(self):
        values=['volume','change','newest','symbol']
        self.query_one('#st-sort',Select).value=values[(values.index(self.sort)+1)%len(values)]

    def action_back(self):
        if isinstance(self.focused,Input):
            self.query_one(TokensTable).query_one('DataTable').focus()
        elif self._standalone:
            self.app.exit()
        else:
            self.app.pop_screen()
