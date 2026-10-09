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
        assert 'trades unavailable' in text
        app.screen.query_one(DataTable).focus()
        await pilot.press('enter')
        await pilot.pause()
        text = painted(app)
        assert 'MOCK' not in text and 'DexScreener' in text and 'Contract' in text
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
        assert 'unavailable' in text.lower()
        assert '0 deployed' not in text and 'No matching tokens' not in text
