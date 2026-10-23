"""Sworn uses the shared reader lifecycle; UI handlers only send intent."""
from textual import events, on
from textual.binding import Binding
from textual.widgets import DataTable, Input

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.sworn.explorer import SwornExplorer
from maxpane_dashboard.widgets.sworn.details import SwornDetailScreen
from maxpane_dashboard.widgets.sworn.art import SwornArt


class SwornScreen(DashboardScreen):
    GAME_NAME = 'SWORN'
    REFRESH_WORKER_NAME = 'sworn-refresh'
    PANELS = ((SwornExplorer, keys('sworn_supply', 'sworn_rows', 'sworn_selected',
                'sworn_selection', 'sworn_error', 'sworn_block', 'sworn_observed_at')),)
    BINDINGS = [Binding('/', 'search', show=False), Binding('[', 'page(1)', show=False),
                Binding(']', 'page(-1)', show=False), Binding('escape', 'list', show=False)]
    DEFAULT_CSS = '''
    SwornScreen {background: $background; color: $text;}
    SwornScreen > SwornExplorer {height: 1fr; padding: 0 1;}
    '''

    def compose(self):
        yield SwornExplorer()
        yield StatusBar()

    def on_mount(self):
        self.call_after_refresh(self.action_list)

    @on(events.ScreenSuspend)
    def _release_art(self):
        self.query_one(SwornArt).release()

    @on(events.ScreenResume)
    def _resume_art(self):
        self.query_one(SwornArt).resume()

    def _prime_status_bar(self, bar):
        bar.set_key_hints('/ find · [ ] page · enter detail')

    def on_sworn_explorer_select(self, event):
        event.stop(); self._select(event.value)

    def _select(self, value, *, inspect=False):
        value = str(value).strip().lower() if value is not None else None
        value = value or None
        self.query_one(SwornExplorer).request(value, inspect=inspect)
        self._data_manager.select(value)
        self.start_refresh()

    def on_input_submitted(self, event):
        if event.input.id == 'sworn-search':
            event.stop(); self._select(event.value.strip() or None)
            self.action_list()

    def action_search(self):
        self.query_one(Input).focus()

    def action_list(self):
        self.query_one(DataTable).focus()

    def action_page(self, direction):
        panel = self.query_one(SwornExplorer)
        if panel.rows and panel.supply:
            token = (panel.rows[0]['token_id'] + 20 if direction > 0 else panel.rows[-1]['token_id'] - 1)
            self._select(str(max(1, min(panel.supply, token))))

    def action_inspect_card(self, token):
        panel = self.query_one(SwornExplorer)
        if panel.selected and panel.selected['token_id'] == token:
            self.action_inspect()
        else:
            self._select(str(token), inspect=True)

    def action_inspect(self):
        card = self.query_one(SwornExplorer).selected
        if card:
            self.app.push_screen(SwornDetailScreen(card))

    def on_sworn_explorer_inspect(self, event):
        event.stop()
        if self.is_current:
            self.app.push_screen(SwornDetailScreen(event.card))
