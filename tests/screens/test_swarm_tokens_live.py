"""Live presentation and navigation, using only an injected offline provider."""
from copy import deepcopy
import asyncio

import pytest

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
            row.update(market_state='ok', market_read_at=self.snapshot['as_of']-60)

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
        assert 'quotes 5/24' in text and 'as of' in text
        assert '30s poll' not in text
        assert 'TOP TRADED / 24H' in text and 'trades unavailable' not in text
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


async def test_top_traded_includes_old_launches_while_newly_display_keeps_full_totals():
    from maxpane_dashboard.widgets.swarm_tokens import NewlyLaunched, TopTraded, TokensTable
    from tests.screens.test_surf_news_hero_demo import painted as panel_text

    provider = LiveProvider()
    now = provider.snapshot['as_of']
    template = provider.snapshot['tokens'][0]
    rows = [dict(template, id=f"new-{i}", symbol=f"NEW{i}", chain="base",
                 launched_at=now-i, volume_24h=100+i) for i in range(8)]
    rows.append(dict(template, id="old", symbol="OLD", launched_at=now-86400*365,
                     volume_24h=1000))
    provider.snapshot['tokens'] = rows
    app = LiveApp(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        assert screen.snapshot['metrics']['new_24h'] == 8
        assert screen.query_one(TokensTable).query_one(DataTable).row_count == 9
        newly = panel_text(app, screen.query_one(NewlyLaunched))
        assert "NEW6" in newly and "NEW7" not in newly
        ranked = panel_text(app, screen.query_one(TopTraded))
        assert ranked.index("OLD") < ranked.index("NEW7")
        assert "NEW2" in ranked and "NEW1" not in ranked
        await pilot.press('c', 'c')
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "OLD" not in panel_text(app, screen.query_one(TopTraded))
        assert "NEW7" in panel_text(app, screen.query_one(TopTraded))


@pytest.mark.parametrize("failure", [False, True])
async def test_actual_pending_token_refresh_animates_shared_footer_then_clears(failure):
    from maxpane_dashboard.widgets.status_bar import StatusBar

    class ControlledProvider(LiveProvider):
        def __init__(self):
            super().__init__()
            self.started, self.release = asyncio.Event(), asyncio.Event()
            self.block = False

        async def fetch_and_compute(self):
            if self.block:
                self.started.set()
                await self.release.wait()
                if failure:
                    raise RuntimeError("controlled source failure")
            return await super().fetch_and_compute()

    provider = ControlledProvider()
    app = LiveApp(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "loading" not in painted(app).splitlines()[-1]
        provider.block = True
        app.screen.action_refresh()
        await asyncio.wait_for(provider.started.wait(), 1)
        app.screen._tick_loading()
        await pilot.pause()
        bar = app.screen.query_one(StatusBar)
        first = painted(app).splitlines()[-1]
        assert "loading" in first and "SC" in painted(app)
        assert bar._loading_timer is not None
        bar._tick_loading()
        await pilot.pause()
        assert painted(app).splitlines()[-1] != first
        provider.release.set()
        await app.workers.wait_for_complete()
        app.screen._tick_loading()
        await pilot.pause()
        assert "loading" not in painted(app) and "SC" in painted(app)
        assert bar._loading_timer is None
