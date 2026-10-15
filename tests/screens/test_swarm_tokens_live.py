"""Live presentation and navigation, using only an injected offline provider."""
from copy import deepcopy

from textual.widgets import Static, DataTable

from maxpane_dashboard.data.swarm_tokens_demo import demo_snapshot
from maxpane_dashboard.demos.swarm_tokens import SwarmTokensDemo
from maxpane_dashboard.screens.swarm_tokens import SwarmTokensScreen
from maxpane_dashboard.themes import THEMES
from tests.screens.test_swarm_tokens import painted


class LiveProvider:
    is_mock = False
    def __init__(self):
        self.snapshot = demo_snapshot()
        self.snapshot['is_mock'] = False
        self.snapshot['sources'] = {
            'catalogue': {'state': 'ok', 'as_of': self.snapshot['as_of'], 'complete': True},
            'markets': {'state': 'partial', 'known': 5, 'total': 24, 'as_of': self.snapshot['as_of']-60},
            'trades': {'state': 'unavailable', 'known': 0, 'total': 24, 'as_of': None},
        }
        self.snapshot['tokens'][0].update(token_address='0x'+'a'*40, chain_id=1,
            market_source='DexScreener', market_read_at=self.snapshot['as_of']-60,
            market_state='ok', liquidity_state='unknown')
        for row in self.snapshot['tokens'][:5]:
            row['market_state'] = 'ok'

    async def fetch_and_compute(self):
        return deepcopy(self.snapshot)


class LiveApp(SwarmTokensDemo):
    def __init__(self, provider=None):
        super().__init__()
        self.provider = provider or LiveProvider()

    def on_mount(self, event):
        event.prevent_default()
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = 'matrix'
        self.push_screen(SwarmTokensScreen(self.provider, standalone=True))


async def test_live_screen_has_coverage_and_explorer_details_without_mock_label():
    app = LiveApp()
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        text = painted(app)
        assert 'MOCK' not in text
        assert 'quotes 5/24' in text and 'as of' in text and '30s' in text
        assert 'ACTIVITY' in text and 'trades unavailable' not in text
        app.screen.query_one(DataTable).focus()
        await pilot.press('enter')
        await pilot.pause()
        text = painted(app)
        assert 'MOCK' not in text and 'DexScreener' in text and 'ARTIFACTS' in text
        strips = app.screen._compositor.render_strips()
        segments = [seg for strip in strips for seg in strip if seg.style]
        assert any(seg.style.link == 'https://etherscan.io/address/0x'+'a'*40 for seg in segments)
        assert any('copy_address' in str(seg.style.meta) for seg in segments)


async def test_live_unavailable_does_not_paint_zero_tokens():
    provider = LiveProvider()
    provider.snapshot.update(tokens=None, activity=None)
    provider.snapshot['sources']['catalogue'] = {'state':'unavailable','as_of':None,'complete':False}
    app = LiveApp(provider)
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        text = painted(app)
        assert 'unavailable' not in text.lower() and '—' in text
        assert '0 deployed' not in text and 'No matching tokens' not in text


async def test_rack_heroes_follow_native_chain_filter_and_source_clocks():
    from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard

    provider = LiveProvider()
    now = provider.snapshot['as_of']
    rows = provider.snapshot['tokens']
    provider.snapshot['tokens'] = [rows[0], rows[1], rows[3]]
    for row in provider.snapshot['tokens']:
        row.update(market_state='ok', market_read_at=now-60,
                   liquidity_state='ok', liquidity_read_at=now-120)
    app = LiveApp(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        cards = list(app.screen.query(NewsHeroCard))
        assert len(cards) == 6 and {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert set(app.screen.snapshot['tokens_hero']) == {
            'tokens', 'volume', 'liquidity', 'pools', 'momentum', 'top_volume'}
        from tests.screens.test_surf_news_hero_demo import painted as card_text
        assert any('tracked' in line and '3' in line
                   for line in card_text(app, cards[0]).splitlines())
        assert '3/3 known' in card_text(app, cards[1])
        assert cards[1].data.read_ts == now-60
        assert cards[2].data.read_ts == now-120
        await pilot.press('c', 'c')  # all -> Ethereum -> Base
        await pilot.pause()
        assert [row['symbol'] for row in app.screen.snapshot['tokens']] == ['TESTER']
        assert any('tracked' in line and '1' in line
                   for line in card_text(app, cards[0]).splitlines())
        assert '1/1 known' in card_text(app, cards[1])
        assert 'TESTER' in card_text(app, cards[5])
        assert 'MEAT' not in card_text(app, cards[5]) and 'SC' not in card_text(app, cards[5])
        assert app.screen.snapshot['tokens_hero']['volume']['amount'] == 14800
