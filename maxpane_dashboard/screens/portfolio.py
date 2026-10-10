"""Approved wallet overview with live sources and an isolated offline preview."""
import asyncio

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Select, Static

from maxpane_dashboard.analytics.portfolio import project_snapshot
from maxpane_dashboard.screens.dashboard_screen import keys
from maxpane_dashboard.screens.swarm_tokens import SwarmTokensScreen, DemoStatusBar
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.widgets.address import address_text, is_address
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.portfolio import (
    EXPLORER, PortfolioHero, PortfolioTable, ClaimableTokens,
    PortfolioActivity, PortfolioMovers, PortfolioDetail,
)
from maxpane_dashboard.widgets.portfolio.filter import PortfolioFilterEditor

KEY_HINTS = 'w wallet · f filters · / find · c chain · o sort · enter details · r reload · esc hub'

#: Measured in the composed screen after the 149×45 mock preview (2026-10-10).
#: Width sweep 138–150: 144 scrolls, 145 fits; the inherited 143-column canvas
#: plus viewport padding binds width. Height sweep 28–38: 34 scrolls, 35 fits.
#: The hero, two-row wallet/filter context, eleven-row summaries, separator and
#: table floor retain every field. The table scrolls internally for long wallets;
#: this pin describes the fixed chrome, not a maximum number of positions.
#: Narrow/short screens retain all ten columns with outer scrolling and hints.
#: Live 118-token capture re-swept over 138–150 columns and 28–38 rows on
#: 2026-10-10: the same 145×35 boundary, including source/coverage headings.
PORTFOLIO_FULL_LAYOUT_COLUMNS = 145
PORTFOLIO_FULL_LAYOUT_ROWS = 35


class PortfolioScreen(SwarmTokensScreen):
    GAME_NAME = 'PORTFOLIO'
    REFRESH_WORKER_NAME = 'portfolio-refresh'
    PANELS = (
        (PortfolioHero, lambda data: {'metrics': data.get('metrics') if data.get('wallet') else {'wallet_required': True}}),
        (PortfolioTable, keys('tokens', 'as_of')),
        (ClaimableTokens, keys('claimable')),
        (PortfolioMovers, keys('gainers', 'losers')),
        (PortfolioActivity, keys('activity', 'tokens')),
    )
    BINDINGS = [Binding('w', 'set_wallet', show=False)]
    DEFAULT_CSS = '''
    PortfolioScreen #st-body { min-height: 34; }
    PortfolioScreen #pf-context { height: 2; padding: 0 1; color: $text-muted; text-wrap: nowrap; }
    PortfolioScreen #pf-separator { height: 1; color: $panel; padding: 0 1; }
    '''

    def __init__(self, manager, poll_interval=None, name='portfolio', *, standalone=False, **kwargs):
        if poll_interval is None:
            poll_interval = 30 if getattr(manager, 'is_mock', False) else 5
        super().__init__(manager, poll_interval, name=name, standalone=standalone, **kwargs)
        self.GAME_NAME = 'PORTFOLIO · MOCK DATA' if self._is_mock else 'PORTFOLIO'
        self.assets, self.sort = 'all', 'value'
        self._wallet_generation = 0

    def compose(self):
        with VerticalScroll(id='st-viewport'):
            with Vertical(id='st-body'):
                yield PortfolioHero()
                yield Static(Text('MOCK DATA' if self._is_mock else 'PORTFOLIO'), id='pf-context')
                with Vertical(id='st-content'):
                    with Vertical(id='st-market'):
                        with Horizontal(id='st-summary'):
                            yield PortfolioActivity()
                            yield ClaimableTokens()
                            yield PortfolioMovers()
                        yield Static('─' * 160, id='pf-separator')
                        yield PortfolioTable()
                    yield PortfolioFilterEditor()
        bar = DemoStatusBar()
        bar.is_mock = self._is_mock
        yield bar

    async def _fetch_data(self):
        generation = self._wallet_generation
        raw = await self._data_manager.fetch_and_compute()
        if generation != self._wallet_generation or raw.get('wallet') != self._data_manager.wallet:
            if generation != self._wallet_generation:
                self.call_after_refresh(self.action_refresh)
            raise asyncio.CancelledError('obsolete wallet snapshot')
        return project_snapshot(raw, chain=self.chain, query=self.search_query,
                                lp_state=self.lp_state, assets=self.assets, sort=self.sort)

    def _prime_status_bar(self, bar):
        hints = KEY_HINTS.replace('esc hub', 'esc quit') if self._standalone else KEY_HINTS
        bar.set_key_hints(hints if self._is_mock else hints.replace('reload', 'refresh'))

    def _chrome(self):
        viewport = self.query_one('#st-viewport', VerticalScroll)
        editor = self.query_one(PortfolioFilterEditor)
        editor.styles.width = viewport.scrollable_content_region.width
        if self._filter_open:
            self.call_after_refresh(editor.on_resize)
        wallet = self._data_manager.wallet
        context = Text('')
        if self._is_mock:
            context.append('MOCK DATA · ', style='yellow')
        if is_address(wallet):
            context += Text('Wallet: ') + address_text(wallet, width=17, explorer=EXPLORER)
        else:
            context += Text('Example wallet' if wallet else 'Set a wallet with w')
        context += Text(' · w change' + (' · example positions; no wallet reads' if self._is_mock else ''), style='dim white')
        hints = (' · ‹ widen' if viewport.show_horizontal_scrollbar else '')
        hints += ' · ‹ taller' if viewport.show_vertical_scrollbar else ''
        context += Text(hints, style='yellow')
        context += Text('\n' + {'all': 'All chains', 'eth': 'Ethereum', 'base': 'Base', 'rh': 'Robinhood'}[self.chain])
        context += Text(' · ' + {'all': 'Held + claimable', 'held': 'Held', 'claimable': 'Claimable'}[self.assets])
        context += Text(f' · LP: {self.lp_state} · sort: {self.sort}')
        if self.search_query:
            context += Text(' · search: ' + clip(flatten(self.search_query), 32))
        self.query_one('#pf-context', Static).update(context)
        total = (self.snapshot.get('metrics') or {}).get('total')
        sources = self.snapshot.get('sources') or {}
        balances, claims = sources.get('balances') or {}, sources.get('claims') or {}
        incomplete = sources and (not balances.get('complete') or not claims.get('complete'))
        count = ('Set a wallet' if not wallet else 'Loading...' if not self.snapshot else
                 'unavailable' if total is None else '0 known matches' if total == 0 and incomplete else
                 'No matching tokens' if total == 0 else f'{total} tokens')
        heading = 'PORTFOLIO · ' + count
        if sources:
            heading += (f" · balances {balances.get('checked', 0)}/{balances.get('total') if balances.get('total') is not None else '?'}"
                        f" · {balances.get('state', 'pending')} · as of {hhmm(balances.get('as_of'))}"
                        f" · claims {claims.get('checked', 0)}/{claims.get('total') if claims.get('total') is not None else '?'}")
            catalogue = sources.get('catalogue') or {}
            if not catalogue.get('coverage_complete', catalogue.get('complete')):
                heading += ' · scan incomplete'
            self.query_one(ClaimableTokens).query_one('.panel-title', Static).update(Text(
                f"CLAIMABLE · {claims.get('state', 'pending')} · as of {hhmm(claims.get('as_of'))}", style='bold'))
            trades = sources.get('trades') or {}
            self.query_one(PortfolioActivity).query_one('.panel-title', Static).update(Text(
                f"MARKET ACTIVITY · {trades.get('state', 'pending')}", style='bold'))
        self.query_one(PortfolioTable).query_one('.panel-title', Static).update(Text(heading, style='bold'))

    def _show_filter(self, editing):
        super()._show_filter(editing)
        if not editing:
            self._prime_status_bar(self.query_one(DemoStatusBar))

    def action_filter(self):
        if self._filter_open:
            self._apply_filter()
            return
        editor = self.query_one(PortfolioFilterEditor)
        editor.set_values(dict(chain='any' if self.chain == 'all' else self.chain,
                               liquidity='any' if self.lp_state == 'all' else self.lp_state,
                               assets='any' if self.assets == 'all' else self.assets,
                               sort='any' if self.sort == 'value' else self.sort, query=self.search_query))
        self._show_filter(True)
        self.call_after_refresh(lambda: editor.query_one(Select).focus())

    def _apply_filter(self):
        values = self.query_one(PortfolioFilterEditor).values()
        self.chain = 'all' if values['chain'] == 'any' else values['chain']
        self.lp_state = 'all' if values['liquidity'] == 'any' else values['liquidity']
        self.assets = 'all' if values['assets'] == 'any' else values['assets']
        self.sort = 'value' if values['sort'] == 'any' else values['sort']
        self.search_query = values['query'].strip()
        self._show_filter(False)
        self.action_refresh()
        self.call_after_refresh(lambda: self.query_one(DataTable).focus())

    def action_sort(self):
        if not self._filter_open:
            values = ['value', 'claimable', 'volume', 'change', 'newest', 'symbol']
            self.sort = values[(values.index(self.sort) + 1) % len(values)]
            self.action_refresh()

    def on_tokens_table_selected(self, event):
        event.prevent_default()
        event.stop()
        if event.token:
            self.app.push_screen(PortfolioDetail(event.token, is_mock=self._is_mock, as_of=self.snapshot.get('as_of')))

    def action_set_wallet(self):
        if not self._filter_open:
            self.app.push_screen(WalletInputScreen(), callback=self._wallet_entered)

    def _wallet_entered(self, address):
        if address and self._data_manager.set_wallet(address):
            self._wallet_generation += 1
            self.snapshot = {}
            self.query_one(PortfolioHero).update_data(None)
            self.query_one(PortfolioTable).update_data([], None)
            self.query_one(ClaimableTokens).update_data([])
            self.query_one(PortfolioMovers).update_data([], [])
            self.query_one(PortfolioActivity).update_data([], [])
            self._chrome()
            self.call_after_refresh(self.action_refresh)
