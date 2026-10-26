"""Wallet-level Swarm activity; A/B navigation projects retained facts."""
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import keys
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.screens.wallet_input import WalletInputScreen
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf_nft.detail import source_url
from maxpane_dashboard.widgets.surf_wallet import WalletBody, EXPLORER


#: Measured 2026-10-26 with the production Matrix stylesheet and live facts.
#: The owner preview was 149 columns by 45 rows, in both A and B.
#: One row contains six complete nine-row heroes.
#: Secondary counts occupy their footers rather than a second card row.
#: A has four eight-row insight panels below the heroes.
#: CREATED shares its next row with the selected path and attention items.
#: RECORD keeps a six-row floor and scrolls its observed requests.
#: B shares its body between the artifact list and independently scrolling detail.
#: The payment widget sits beneath B's list.
#: The one-row screen title and shared footer stay outside WalletBody.
#: The body floor is 43 rows, including its own vertical padding.
#: Therefore a complete body viewport begins at 45 terminal rows.
#: The measured body width floor is 145 terminal columns.
#: Both views were sampled at every width from 144 through 149.
#: Each width was crossed with heights 44, 45 and 46.
#: At 145 by 45 neither outer scroll direction has remaining extent.
#: The same is true at all measured larger sizes.
#: At 144 by 45 the horizontal extent is two cells.
#: Its horizontal scrollbar also creates one row of vertical overflow.
#: At 145 by 44 the vertical extent is two rows and horizontal extent one.
#: At 146 by 44 only the one-row vertical extent remains.
#: These scrollbar interactions are measured, not inferred from the CSS floor.
#: At 100 by 30 both directions remain reachable and resize restores the view.
#: Artifact identity survives narrow scrolling and A/B navigation.
#: The nine-row hero frames remain intact inside the scrolled layout.
#: Table columns may shorten names while retaining address actions.
#: Evidence prose may scroll within the detail panel even above these floors.
#: The pin does not promise that every record fits simultaneously.
#: Unread and observed-empty facts use the same geometry.
#: Boundary regressions sample both sides of each floor in both views.
#: The address sweep imports these measurements instead of retyping them.
#: No application-wide minimum or existing dashboard pin changes here.
SURF_WALLET_FULL_LAYOUT_COLUMNS = 145
SURF_WALLET_FULL_LAYOUT_ROWS = 45


class SurfWalletScreen(SurfDashboardScreen):
    GAME_NAME = 'WALLET / SWARM'
    JOIN_STARTUP_PREFETCH = False
    REFRESH_WORKER_NAME = 'surf-wallet-refresh'
    PANELS = ((WalletBody, keys('wallet_snapshot')),)
    BINDINGS = [Binding('escape','back',show=False), Binding('w','set_wallet',show=False),
                Binding('r','refresh',show=False)]
    DEFAULT_CSS = '''
    SurfWalletScreen {background: $background; color: $text;}
    SurfWalletScreen #wallet-header {height: 1; color: $text-muted; content-align: center middle;}
    SurfWalletScreen WalletBody {height: 1fr;}
    '''

    def __init__(self, manager, poll_interval=30, name='surf-wallet', *, view_state=None, **kwargs):
        super().__init__(manager,poll_interval,name=name,**kwargs)
        self._view_state = view_state if isinstance(view_state,dict) else {}
        self.snapshot = {}

    def compose(self):
        yield Static(Text('WALLET / SWARM'),id='wallet-header')
        yield WalletBody(view_state=self._view_state)
        yield SurfStatusBar()

    def _loading_view(self):
        return 'wallet'

    def on_mount(self):
        self.call_after_refresh(self.query_one(WalletBody).focus_selection)

    def _prime_status_bar(self, bar):
        detail = self.query_one(WalletBody).view == 'detail'
        bar.set_key_hints('arrows select · '+('esc overview' if detail else 'enter artifact · esc boardroom')+
                          ' · tab records · w wallet · r refresh')

    def on_wallet_body_view_changed(self,event):
        event.stop()
        self._prime_status_bar(self.query_one(SurfStatusBar))
        self._update_title({'wallet_snapshot':self.snapshot})

    def _update_title(self,data):
        self.snapshot = data.get('wallet_snapshot') or {}
        wallet = self.snapshot.get('wallet') or self._view_state.get('wallet')
        if wallet:
            self._view_state['wallet'] = wallet
        caption = Text('WALLET / SWARM · ')
        if wallet:
            caption.append_text(address_text(wallet,width=19,explorer=EXPLORER(1)))
        else:
            caption.append('w to choose wallet')
        stamp=self.snapshot.get('as_of')
        caption.append(' · as of '+(hhmm(stamp) if isinstance(stamp,(float,int)) else '—'))
        caption.append(' · w wallet · r refresh · '+('Esc overview' if self.query_one(WalletBody).view=='detail' else 'Enter detail · Esc back'))
        self.query_one('#wallet-header',Static).update(caption)

    def action_set_wallet(self):
        self.app.push_screen(WalletInputScreen(),callback=self._wallet_entered)

    def _wallet_entered(self,address):
        if address and self._data_manager.set_wallet(address):
            self._view_state['wallet']=address.lower()
            # Clear the identity immediately; ReaderHandle dispatches the command
            # asynchronously and its next result must not repaint the old wallet.
            fresh={'wallet':address.lower()}
            self.query_one(WalletBody).update_data(wallet_snapshot=fresh)
            self._update_title({'wallet_snapshot':fresh})
            self.call_after_refresh(self.action_refresh)

    def action_back(self):
        if not self.query_one(WalletBody).back():
            self.app.pop_screen()

    def action_open_wallet_source(self,index):
        links=self.query_one(WalletBody).source_links
        if type(index) is int and 0<=index<len(links) and (url:=source_url(links[index])):
            self.app.open_url(url)
