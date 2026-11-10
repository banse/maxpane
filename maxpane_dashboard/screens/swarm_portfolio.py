"""Portfolio A with the cached B workspace in a native modal."""
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Input, Select, Static

from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.portfolio.overview import SwarmPortfolioOverview, EXPLORER
from maxpane_dashboard.widgets.portfolio.inspector import SwarmPortfolioInspector
from maxpane_dashboard.widgets.portfolio.filter import PortfolioFilterEditor


#: Measured 2026-11-09 after the live 149-by-45 overview and popup were shown.
#: Production minimal.tcss and the Matrix theme supply the real containers.
#: The source capture contains 534 assets, eight positions and 520 rewards.
#: The sweep also uses a representative snapshot, extreme labels and values,
#: an unread loading snapshot and a successfully empty wallet observation.
#: All five payload classes have the same outer geometry.
#: Six nine-row rack cards precede three panel rows, with filters beside HOLDINGS.
#: The inner layout is 143 columns wide at its floor.
#: Its own two padding cells and the reserved two-cell scrollbar gutter count.
#: The first whole horizontal viewport is 147 terminal columns.
#: The broad probe started at 125 columns and extended through 155.
#: The permanent boundary set covers 120, 146, 147, 148 and 160 columns.
#: At 146 columns the body has exactly one column of horizontal extent.
#: At 147 columns the rightmost SEATS frame is wholly inside the viewport.
#: All six cards keep the same side padding; the SEATS caption is Identity.md.
#: Every installed table header and column fits at that boundary.
#: The rewards table needs 54 columns and has 55 after its own gutter.
#: The widest left table is NFT inventory, with 73 columns inside 83.
#: Table token/name budgets include both cells of the shared copy icon.
#: Addresses and linked names retain their copy and chain-explorer actions.
#: Card-footer refinement measured 2026-11-10 after the live 149-by-45 preview.
#: The filter summary shares the one-line HOLDINGS title; long queries ellipsize.
#: One blank row separates the cards from the panel titles and filter editor.
#: The content floor is 35 rows inside two rows of body padding.
#: The title and shared status footer each consume one terminal row.
#: The first whole vertical viewport is 39 terminal rows.
#: The broad height probe started at 30 rows and continued through 48.
#: The permanent boundary set covers 24, 38, 39, 40 and 50 rows.
#: At 38 rows the body has exactly one row of vertical extent.
#: At 147 by 39 neither outer scroll direction has remaining extent.
#: The width was rechecked from 125 through 155 and remains 147.
#: The native filter editor replaces the panel area with the same 25-row floor.
#: The panel rows share extra height at 9:8:6, preserving their minimum content.
#: On 2026-11-11 TOKEN UTILITIES was hidden and eligibility spans the lower right.
#: It shares the STAKES top and NFT inventory bottom, reclaiming the row gap too.
#: At 149 by 45 eligibility grows to 19 rows; the visible tables retain their size.
#: Broad probes over 125-155 columns and 30-48 rows still measure 147 by 39.
#: At 149 by 45 the panel area is 31 rows and the NFT table is six rows tall.
#: Tables leave exactly one blank row before the status bar at 45 and 60 rows.
#: At 80 by 24 its fields use the shared two-column compact editor layout.
#: Below either boundary the header reports actual viewport overflow.
#: Horizontal overflow can add a scrollbar row and light both hints.
#: At 80 by 24 the four body corners remain reachable by scrolling.
#: The unbounded tables and eligibility evidence scroll within their panels.
#: Long names may shorten with an ellipsis without widening their columns.
#: These pins certify the overview, not simultaneous visibility of every row.
#: The popup keeps the native 110-column frame and its own internal scrolling.
#: No application-wide or existing dashboard minimum changes here.
SWARM_PORTFOLIO_FULL_LAYOUT_COLUMNS = 147
SWARM_PORTFOLIO_FULL_LAYOUT_ROWS = 39


class SwarmPortfolioScreen(SurfDashboardScreen):
    GAME_NAME = 'PORTFOLIO'
    REFRESH_WORKER_NAME = 'swarm-portfolio-refresh'
    PANELS = ((SwarmPortfolioOverview, lambda data: {'snapshot': data}),)
    BINDINGS = [Binding('escape','back',show=False), Binding('w','set_wallet',show=False),
                Binding('f','filters',show=False), Binding('slash','search',show=False),
                Binding('r','scan_refresh',show=False)]
    DEFAULT_CSS = '''
    SwarmPortfolioScreen {background: $background; color: $text;}
    SwarmPortfolioScreen #portfolio-header {height: 1; color: $text-muted; content-align: center middle; text-wrap: nowrap; text-overflow: ellipsis;}
    SwarmPortfolioScreen SwarmPortfolioOverview {height: 1fr;}
    '''

    def __init__(self, manager, poll_interval=30, name='swarm-portfolio', *, view_state=None, **kwargs):
        super().__init__(manager, poll_interval, name=name, **kwargs)
        self._view_state = view_state if isinstance(view_state, dict) else {}
        self._title_data = {}
        self._filter_open = False

    def compose(self):
        yield Static(Text('PORTFOLIO'), id='portfolio-header')
        yield SwarmPortfolioOverview(view_state=self._view_state)
        yield SurfStatusBar()

    def on_mount(self):
        self.call_after_refresh(self.query_one(SwarmPortfolioOverview).focus_selection)

    def _prime_status_bar(self, bar):
        bar.set_key_hints('arrows select · enter inspect · / search · f filters · w wallet · r rescan · esc back')

    def _update_title(self, data):
        self._title_data = {'wallet': data.get('wallet'), 'as_of': data.get('as_of')}
        self.call_after_refresh(self._chrome)

    def on_resize(self):
        self.call_after_refresh(self._chrome)

    def _chrome(self):
        data = self._title_data
        wallet = data.get('wallet')
        text = Text('PORTFOLIO · ')
        body = self.query_one(SwarmPortfolioOverview)
        if self._filter_open:
            self.query_one(PortfolioFilterEditor).styles.width = body.scrollable_content_region.width
        if body.max_scroll_x > 0:
            text.append('‹ widen · ')
        if body.max_scroll_y > 0:
            text.append('‹ taller · ')
        if wallet:
            self._view_state['wallet'] = wallet
            text.append_text(address_text(wallet, width=19, explorer=EXPLORER(1)))
        else:
            text.append('w to choose wallet')
        text.append(' · as of '+(hhmm(data.get('as_of')) if data.get('as_of') else '—'))
        text.append(' · f apply · Esc cancel · Tab fields' if self._filter_open else
                    ' · w wallet · f filters · / search · Enter inspect · Esc back')
        self.query_one('#portfolio-header', Static).update(text)

    def on_swarm_portfolio_overview_inspect(self, event):
        event.stop()
        self.app.push_screen(SwarmPortfolioInspector(event.row, event.snapshot, record_kind=event.record_kind))

    def action_filters(self):
        if self._filter_open:
            self._apply_filter()
            return
        editor = self.query_one(PortfolioFilterEditor)
        editor.set_values(dict(chain=self._view_state.get('chain', 'any'),
                               sort=self._view_state.get('sort', 'any'),
                               sale='show' if self._view_state.get('show_no_sale') else 'any',
                               query=self._view_state.get('query', '')))
        self._show_filter(True)
        self.call_after_refresh(lambda: editor.query_one(Select).focus())

    def _show_filter(self, editing):
        self._filter_open = editing
        self.query_one('#pf-panels').display = not editing
        self.query_one(PortfolioFilterEditor).display = editing
        bar = self.query_one(SurfStatusBar)
        if editing:
            bar.set_key_hints('f apply · esc cancel · tab fields · APPLY FILTER / RESET ALL')
        else:
            self._prime_status_bar(bar)
            self.call_after_refresh(self.query_one(SwarmPortfolioOverview).focus_selection)
        self.call_after_refresh(self._chrome)

    def _apply_filter(self):
        values = self.query_one(PortfolioFilterEditor).values()
        self._view_state.update(chain='all' if values['chain'] == 'any' else values['chain'],
                                sort='value' if values['sort'] == 'any' else values['sort'],
                                show_no_sale=values['sale'] == 'show', query=values['query'].strip())
        self.query_one(SwarmPortfolioOverview)._project()
        self._show_filter(False)

    def on_swarm_tokens_filter_apply_requested(self, event):
        event.stop()
        if self._filter_open:
            self._apply_filter()

    def on_swarm_tokens_filter_reset_requested(self, event):
        event.stop()
        self.query_one(PortfolioFilterEditor).set_values({})

    def action_search(self):
        if not self._filter_open:
            self.action_filters()
        self.call_after_refresh(lambda: self.query_one('#filter-query', Input).focus())

    def action_set_wallet(self):
        self.app.push_screen(WalletInputScreen(), callback=self._wallet_entered)

    def _wallet_entered(self, address):
        if address and self._data_manager.set_wallet(address):
            self._view_state['wallet'] = address.lower()
            self._view_state.pop('selected_id', None)
            fresh = {'wallet': address.lower(), 'state': 'loading'}
            self.query_one(SwarmPortfolioOverview).update_data(snapshot=fresh)
            self._update_title(fresh)
            self.call_after_refresh(self.action_refresh)

    def action_scan_refresh(self):
        self._data_manager.request_refresh()
        self.action_refresh()

    def action_back(self):
        if self._filter_open:
            self._show_filter(False)
        else:
            self.app.pop_screen()
