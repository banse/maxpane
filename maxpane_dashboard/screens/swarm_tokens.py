"""Approved market overview with live and explicitly offline providers."""
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Input, Select, Static

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.swarm_tokens import (
    BestPlays, NewlyLaunched, TokenActivity, TokensHero, TokensTable,
)
from maxpane_dashboard.data.swarm_token_detail import SwarmTokenDetailManager
from maxpane_dashboard.data.reader import ReaderHandle
from maxpane_dashboard.screens.swarm_token_detail import SwarmTokenScreen
from maxpane_dashboard.widgets.swarm_tokens.filter import SwarmTokensFilterEditor

#: Overview remeasured after the live 149x45 panel-order revision (2026-10-10).
#: Compact revision: at 145x32 all twelve table columns, four heroes and
#: the Activity / Newly Launched / Best Plays row fit above All Tokens without
#: an outer scrollbar. At 144x32 or 145x31
#: the viewport scrolls and advertises the reduced space. At 149x45 the
#: table shows twenty data rows, with the remaining rows behind its scrollbar.
#: The table keeps all 24 rows and scrolls internally at every measured size.
#: Widgets retain a 143-column body and 31-row content floor; a vertical
#: scrollbar below the row pin can also require a horizontal one.
#: Rack hero integration, measured after the live 149x45 preview (2026-10-12):
#: six equal nine-row heroes require a 33-row body; 146x34 paints all six
#: outer frames and the native panel/table headers without viewport overflow.
#: At 145x34 the last frame loses one column to the reserved gutter, even
#: though Textual's horizontal scrollbar flag is false. Chrome therefore uses
#: actual scroll extent; 145 advertises widen and 146/147 show complete frames.
#: At 146x33 the body scrolls and advertises taller; 34/35 fit. At 149x45 the
#: table retains all 24 fixture rows and shows eighteen internally scrollable
#: data rows. The width floor remains 143; its gutter is now counted honestly.
SWARM_TOKENS_FULL_LAYOUT_COLUMNS = 146
SWARM_TOKENS_FULL_LAYOUT_ROWS = 34


class DemoStatusBar(StatusBar):
    """Use the shared compact footer for live and demo token dashboards."""
    is_mock = True


class SwarmTokensScreen(SurfDashboardScreen):
    GAME_NAME = 'SWARM TOKENS'
    LOADING_CHROME = "_chrome"
    REFRESH_WORKER_NAME = 'swarm-tokens-refresh'
    # This provider schedules its own sources independently of SURF's prefetch.
    JOIN_STARTUP_PREFETCH = False
    PANELS = (
        (TokensHero, keys('tokens_hero')),
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
    SwarmTokensScreen #st-viewport { height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-body { width: 1fr; min-width: 143; height: 1fr; min-height: 33; }
    SwarmTokensScreen TokensHero { height: 9; margin: 1 0; }
    SwarmTokensScreen #st-content { height: 1fr; min-height: 22; }
    SwarmTokensScreen #st-market { height: 1fr; }
    SwarmTokensScreen TokensTable { height: 1fr; min-height: 10; border: none; }
    SwarmTokensScreen DataTable { height: 1fr; background: $background; scrollbar-size: 1 1; }
    SwarmTokensScreen #st-summary { height: 11; margin-bottom: 1; }
    SwarmTokensScreen NewlyLaunched, SwarmTokensScreen BestPlays, SwarmTokensScreen TokenActivity {
        width: 1fr; height: 1fr; border: none; }
    SwarmTokensScreen TokenActivity, SwarmTokensScreen NewlyLaunched { margin-right: 1; }
    SwarmTokensScreen .panel-title { height: 1; padding: 0 1; margin-bottom: 1; color: $text-muted;
        text-wrap: nowrap; text-overflow: ellipsis; }
    SwarmTokensScreen RichLog { height: 1fr; padding: 0 1; background: $background;
        scrollbar-size: 1 1; }
    SwarmTokensScreen #st-best-body { height: 1fr; padding: 0 1; }
    SwarmTokensScreen SwarmTokensFilterEditor { display: none; }
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
        self._is_mock = getattr(manager, 'is_mock', False)
        self.GAME_NAME = 'SWARM TOKENS · MOCK DATA' if self._is_mock else 'SWARM TOKENS'

    def compose(self):
        with VerticalScroll(id='st-viewport'):
            with Vertical(id='st-body'):
                yield TokensHero()
                with Vertical(id='st-content'):
                    with Vertical(id='st-market'):
                        with Horizontal(id='st-summary'):
                            yield TokenActivity()
                            yield NewlyLaunched()
                            yield BestPlays()
                        yield TokensTable()
                    yield SwarmTokensFilterEditor()
        bar = DemoStatusBar()
        bar.is_mock = self._is_mock
        yield bar

    async def _fetch_data(self):
        raw = await super()._fetch_data()
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
        suffix = (' · ‹ widen' if viewport.max_scroll_x > 0 else '')
        suffix += ' · ‹ taller' if viewport.max_scroll_y > 0 else ''
        chain={'all':'all chains','eth':'Ethereum','base':'Base','rh':'Robinhood'}[self.chain]
        selection=f' · {self.lp_state}' if self.lp_state!='all' else ''
        selection+=f' · search: {flatten(self.search_query)}' if self.search_query else ''
        total=(self.snapshot.get('metrics') or {}).get('total')
        count='—' if total is None else f'{total} tokens' if total else 'No matching tokens'
        sources=self.snapshot.get('sources') or {}
        cat=sources.get('catalogue') or {}
        source_text=''
        if sources:
            source_text=f" · as of {hhmm(cat.get('as_of'))}"
            rows=self.snapshot.get('tokens') or []
            quoted=sum(row.get('market_state')=='ok' and row.get('price_usd') is not None for row in rows)
            source_text+=f" · quotes {quoted}/{len(rows)}"
        self.query_one(TokensTable).query_one('.panel-title',Static).update(Text(
            f'ALL TOKENS{self.loading_suffix} · {count}{suffix} · {chain}{selection} · sort: {self.sort}{source_text}', style='bold'))
        if sources:
            self.query_one(TokenActivity).query_one('.panel-title',Static).update(Text(
                "ACTIVITY",style='bold'))

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

    def on_tokens_table_selected(self,event):
        event.stop()
        if event.token:
            detail = (self._data_manager.token_detail_manager(event.token)
                      if isinstance(self._data_manager, ReaderHandle)
                      else SwarmTokenDetailManager(self._data_manager, event.token))
            self.app.push_screen(SwarmTokenScreen(detail))

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
