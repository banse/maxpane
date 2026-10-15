"""Dedicated selected-token dashboard, reached from the retained market list."""
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar
from maxpane_dashboard.widgets.swarm_token_detail._fmt import metric_label
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.swarm_token_detail import (
    DetailHero, LaunchSummary, ContributorTable, MarketPanel, PositionPanel, ArtifactTable,
)

#: Selected-token body measured after the live BLACKOUT preview at 149x45
#: (2026-10-15). Six native nine-row cards, the 2:1 launch/market body and
#: full-width artifacts fit at 146x44 without an outer scrollbar.
#: Width sweep 140..149 at 45 rows: 145 leaves one column beyond the viewport;
#: 146 is the first complete rightmost card, including the reserved gutter.
#: Height sweep 40..46 at 149 columns: 43 scrolls one line; 44 fits all fixed
#: panel floors. Contributor and artifact tables scroll internally by design.
#: Long objectives have a separate two-line viewport; they do not push status,
#: verdict, record time, site or repository out of the launch summary.
#: The body keeps a 143-column floor and 42-row content floor; title and status
#: bars own one row each. Values here record observation, not CSS arithmetic.
#: Boundary tests mount the real stylesheet at each pin and both neighbors,
#: with complete and unavailable/long-objective payloads. Smaller terminals
#: retain the same body and expose horizontal/vertical scroll plus hints.
SWARM_TOKEN_FULL_LAYOUT_COLUMNS = 146
SWARM_TOKEN_FULL_LAYOUT_ROWS = 44


class TokenStatusBar(StatusBar):
    def _ordinary_status(self, *_args):
        return 'q quit · esc tokens · r refresh · tab panels'


class SwarmTokenScreen(SurfDashboardScreen):
    GAME_NAME = 'SWARM TOKEN'
    LOADING_CHROME = "_chrome"
    REFRESH_WORKER_NAME = 'swarm-token-detail-refresh'
    JOIN_STARTUP_PREFETCH = False
    PANELS = (
        (DetailHero, keys('token', 'launch', 'contributors', 'sources', 'is_mock')),
        (LaunchSummary, keys('token', 'launch', 'sources', 'is_mock')),
        (ContributorTable, keys('contributors', 'sources')),
        (MarketPanel, keys('token')),
        (PositionPanel, keys('token')),
        (ArtifactTable, keys('token', 'artifacts', 'sources', 'is_mock')),
    )
    BINDINGS = [Binding('escape', 'back', show=False), Binding('m', 'back', show=False)]
    DEFAULT_CSS = '''
    SwarmTokenScreen { background: $background; color: $text; }
    SwarmTokenScreen #token-title { height: 1; text-align: center; color: $text-muted;
        background: $boost; text-wrap: nowrap; }
    SwarmTokenScreen #token-viewport { height: 1fr; padding: 0 1; overflow: auto auto;
        scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SwarmTokenScreen #token-body { width: 1fr; min-width: 143; height: 1fr; min-height: 42; }
    SwarmTokenScreen DetailHero { height: 9; margin: 1 0; }
    SwarmTokenScreen #token-middle { height: 1fr; min-height: 22; margin-bottom: 1; }
    SwarmTokenScreen #token-main { width: 2fr; height: 1fr; margin-right: 2; }
    SwarmTokenScreen #token-rail { width: 1fr; height: 1fr; }
    SwarmTokenScreen LaunchSummary { height: 11; }
    SwarmTokenScreen ContributorTable { height: 1fr; min-height: 11; }
    SwarmTokenScreen MarketPanel { height: 12; }
    SwarmTokenScreen PositionPanel { height: 1fr; min-height: 10; }
    SwarmTokenScreen ArtifactTable { height: 8; }
    SwarmTokenScreen DataTable { height: 1fr; background: $background; scrollbar-size: 1 1; }
    SwarmTokenScreen .panel-title { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    '''

    def __init__(self, manager, poll_interval=5, **kwargs):
        super().__init__(manager, poll_interval, **kwargs)
        self.snapshot = {}

    def compose(self):
        yield Static(Text('SURFBOARD · TOKEN'), id='token-title')
        with VerticalScroll(id='token-viewport'):
            with Vertical(id='token-body'):
                yield DetailHero()
                with Horizontal(id='token-middle'):
                    with Vertical(id='token-main'):
                        yield LaunchSummary()
                        yield ContributorTable()
                    with Vertical(id='token-rail'):
                        yield MarketPanel()
                        yield PositionPanel()
                yield ArtifactTable()
        yield TokenStatusBar()

    def _update_title(self, data):
        self.snapshot = data
        self.call_after_refresh(self._chrome)

    def on_resize(self):
        self.call_after_refresh(self._chrome)

    def _chrome(self):
        token = self.snapshot.get('token') or {}
        symbol = metric_label(token.get('symbol')).lstrip('$') or '--'
        name = metric_label(token.get('name'))
        chain = {'eth': 'ETHEREUM', 'base': 'BASE', 'rh': 'ROBINHOOD'}.get(token.get('chain'), '--')
        title = f'SURFBOARD · ${symbol}' + (f' · {name}' if name and name != symbol else '')
        title += f" · {chain} · #{token.get('launch_id') or '--'}"
        if self.snapshot.get('is_mock'):
            title += ' · MOCK DATA'
        viewport = self.query_one('#token-viewport', VerticalScroll)
        suffix = (' · ‹ widen' if viewport.max_scroll_x > 0 else '')
        suffix += ' · ‹ taller' if viewport.max_scroll_y > 0 else ''
        suffix += self.loading_suffix
        title = clip(title, max(1, self.size.width - len(suffix)))
        self.query_one('#token-title', Static).update(Text(title + suffix, style='bold'))

    def action_back(self):
        self.app.pop_screen()

    async def on_unmount(self):
        # Only the selected-token adapter is owned here. The overview and its
        # shared market/source caches remain mounted underneath this screen.
        close = getattr(self._data_manager, 'close', None)
        if close is not None:
            await close()
