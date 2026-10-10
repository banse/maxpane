"""Hub tables and terminal use the same foregrounds as Base Trading."""
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.base.overview.bt_overview_leaderboard import BTOverviewLeaderboard
from maxpane_dashboard.widgets.portfolio import ClaimableTokens, PortfolioTable
from maxpane_dashboard.widgets.surfboard import SurfboardTerminal
from maxpane_dashboard.widgets.swarm_tokens import BestPlays, NewlyLaunched, TokenActivity, TokensTable
from tests.widgets.test_swarm_tokens import NOW, token


class ColorProbe(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    CSS = '''
    BTOverviewLeaderboard { height: 7; }
    TokensTable { height: 15; }
    NewlyLaunched, BestPlays, TokenActivity { height: 12; }
    '''

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self):
        yield BTOverviewLeaderboard()
        yield self.widget

    def on_mount(self):
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'
        self.query_one(BTOverviewLeaderboard).update_data(trending_tokens=[
            dict(symbol='FIRST', price_usd=1, price_change_24h=2),
            dict(symbol='REFERENCE', price_usd=2, price_change_24h=-3),
        ])


def color_at(app, word):
    strips = app.screen._compositor.render_strips()
    y = next(i for i, strip in enumerate(strips) if word in strip.text)
    return app.screen.get_style_at(strips[y].text.index(word), y).color


@pytest.mark.parametrize('widget,values,word', [
    (TokensTable, dict(tokens=[token(symbol='TARGET')], as_of=NOW), 'TARGET'),
    (PortfolioTable, dict(tokens=[token(symbol='TARGET', held_quantity=2)], as_of=NOW), 'TARGET'),
    (NewlyLaunched, dict(newly_launched=[token(symbol='TARGET')], as_of=NOW), 'TARGET'),
    (BestPlays, dict(gainers=[token(symbol='TARGET')], losers=[]), 'TARGET'),
    (ClaimableTokens, dict(claimable=[token(symbol='TARGET', claimable_quantity=2)]), 'TARGET'),
    (TokenActivity, dict(activity=[dict(ts=NOW, kind='BUY', token_id='eth-sc', amount=2)],
                         tokens=[token(symbol='TARGET')]), 'TARGET'),
    (SurfboardTerminal, dict(surfboard_events=[dict(key='1', timestamp=NOW, kind='node',
        state='working', objective='TARGET', token_id=420)]), 'TARGET'),
])
async def test_ordinary_text_matches_native_table_foreground(widget, values, word):
    panel = widget()
    async with ColorProbe(panel).run_test(size=(149, 45)) as pilot:
        panel.update_data(**values)
        for table in panel.query(DataTable):
            table.show_cursor = False
        await pilot.pause()
        assert color_at(pilot.app, word) == color_at(pilot.app, 'REFERENCE')


async def test_terminal_statuses_match_native_positive_and_negative_colors():
    panel = SurfboardTerminal()
    async with ColorProbe(panel).run_test(size=(149, 45)) as pilot:
        panel.update_data(surfboard_events=[
            dict(key='1', timestamp=NOW, kind='node', state='working', objective='Active'),
            dict(key='2', timestamp=NOW, kind='node', state='failed', objective='Failure'),
        ])
        pilot.app.query_one(BTOverviewLeaderboard).query_one(DataTable).show_cursor = False
        await pilot.pause()
        assert color_at(pilot.app, 'working') == color_at(pilot.app, '+2.0%')
        assert color_at(pilot.app, 'failed') == color_at(pilot.app, '-3.0%')
