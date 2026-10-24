"""Surf loading follows actual work, including cached open/reopen reads."""
import asyncio

import pytest
from textual.app import App
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.screens.surf_loading import SurfDashboardScreen, SurfStatusBar


class Provider:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.pending = False
        self.fail = False
        self.reads = 0
        self.projections = 0

    async def fetch_and_compute(self):
        self.reads += 1
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError('read failed')
        return {'value': 'cached 42'}

    def is_loading(self, view=None):
        return self.pending

    def get_snapshot(self):
        self.projections += 1
        return {'value': 'finished 43' if self.reads else 'cached 42'}


class LoadingScreen(SurfDashboardScreen):
    GAME_NAME = 'SURF TEST'
    REFRESH_WORKER_NAME = 'surf-loading-test'
    LOADING_CHROME = '_chrome'

    def compose(self):
        yield Static('', id='title')
        yield Static('cached 42', id='value')
        yield SurfStatusBar()

    def _update_title(self, data):
        self.query_one('#value', Static).update(data['value'])
        self._chrome()

    def _chrome(self):
        self.query_one('#title', Static).update('SURF' + self.loading_suffix)


class LoadingApp(App):
    def __init__(self, provider):
        super().__init__()
        self.provider = provider

    def on_mount(self):
        self.push_screen(LoadingScreen(self.provider, poll_interval=3600))


@pytest.mark.parametrize('failure', [False, True])
async def test_cards_stay_blank_while_visible_reads_animate_only_the_footer(failure, monkeypatch):
    from textual.containers import Vertical
    from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard, HeroRecord
    from tests.widgets.test_card_loading import face, inset_rows

    def forbidden_timer(*args, **kwargs):
        raise AssertionError('cards must not create loading timers')

    monkeypatch.setattr(NewsHeroCard, 'set_interval', forbidden_timer)

    class CardScreen(LoadingScreen):
        def compose(self):
            yield from super().compose()
            with Vertical(id='card-body'):
                yield NewsHeroCard(HeroRecord('static', 'COUNT', 'VALUE', '', digits='--'))

    class CardApp(App):
        def on_mount(self):
            self.push_screen(CardScreen(provider, poll_interval=3600))

    provider = Provider()
    provider.fail = failure
    app = CardApp()
    async with app.run_test(size=(149, 45)) as pilot:
        await provider.started.wait()
        screen = app.screen
        await pilot.pause()
        card = screen.query_one(NewsHeroCard)
        original = face(app, card)
        assert not any(row.strip() for row in inset_rows(app, card))
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen).splitlines()[-1]
        reads, projections = provider.reads, provider.projections
        for _ in range(16):
            screen._tick_loading()
        await pilot.pause()
        assert (provider.reads, provider.projections) == (reads, projections)
        assert face(app, card) == original
        body = screen.query_one('#card-body')
        body.display = False
        await pilot.pause()
        screen._tick_loading()
        assert card._card_loading is False
        body.display = True
        await pilot.pause()
        screen._tick_loading()
        await pilot.pause()
        assert face(app, card) == original
        provider.release.set()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' not in painted(screen).splitlines()[-1]
        assert face(app, card) == original
        provider.release.clear()
        provider.started.clear()
        screen.start_refresh()
        await provider.started.wait()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen).splitlines()[-1]
        assert face(app, card) == original
        await app.push_screen(Screen())
        assert card._card_loading is False
        assert screen._loading_timer is None
        provider.started.clear()
        app.pop_screen()
        await provider.started.wait()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen).splitlines()[-1]
        assert face(app, card) == original
        assert '<>' not in painted(screen) and '◇' not in painted(screen)
        provider.release.set()


def painted(screen):
    return '\n'.join(strip.text for strip in screen._compositor.render_strips())


@pytest.mark.parametrize('failure', [False, True])
async def test_pending_open_and_reopen_clears_on_success_or_failure(failure):
    provider = Provider()
    app = LoadingApp(provider)
    async with app.run_test() as pilot:
        screen = app.screen
        await provider.started.wait()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen)
        assert 'cached 42' in painted(screen)
        provider.release.set()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' not in painted(screen)
        await app.push_screen(Screen())
        assert screen._loading_timer is None
        provider.started.clear()
        provider.release.clear()
        provider.fail = failure
        app.pop_screen()
        await provider.started.wait()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen)
        provider.release.set()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' not in painted(screen)
        assert 'unavailable' not in painted(screen)
        assert 'stale' not in painted(screen)


async def test_background_completion_paints_passive_snapshot_without_refetch():
    provider = Provider()
    provider.release.set()
    provider.pending = True
    app = LoadingApp(provider)
    async with app.run_test() as pilot:
        screen = app.screen
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' in painted(screen)
        provider.pending = False
        screen._tick_loading()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'finished 43' in painted(screen)
        assert 'loading' not in painted(screen)
        assert provider.reads == 1
        assert provider.projections == 2  # Entry cache plus completed background read.


def test_every_surf_view_uses_shared_loading_lifecycle():
    from maxpane_dashboard.screens.surf import SurfScreen
    from maxpane_dashboard.screens.surfboard import SurfboardScreen
    from maxpane_dashboard.screens.swarm_tokens import SwarmTokensScreen
    from maxpane_dashboard.screens.swarm_token_detail import SwarmTokenScreen
    for cls in (SurfScreen, SurfboardScreen, SwarmTokensScreen, SwarmTokenScreen):
        assert issubclass(cls, SurfDashboardScreen)


async def test_native_body_switch_refreshes_and_shows_loading():
    from maxpane_dashboard.screens.surf import SurfScreen
    from tests.screens.test_surf_screen import _TrackingBlockingManager, _ThemedHarness
    manager = _TrackingBlockingManager()
    manager.release.set()
    screen = SurfScreen(manager, poll_interval=3600)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        assert manager.calls == 1
        for mode in ('launchpad', 'dashboard'):
            manager.entered.clear()
            manager.release.clear()
            screen.open_mode(mode)
            await asyncio.wait_for(manager.entered.wait(), timeout=2)
            screen._tick_loading()
            await pilot.pause()
            assert 'loading' in painted(screen)
            manager.release.set()
            await app.workers.wait_for_complete()
            screen._tick_loading()
            await pilot.pause()
            assert 'loading' not in painted(screen)
        assert manager.calls == 3


async def test_fast_token_enrichment_repaints_before_the_first_loading_tick():
    from maxpane_dashboard.data.swarm_tokens_manager import SwarmTokensManager
    from tests.data.test_swarm_tokens_live import Source, Pages, Market, rows
    from tests.screens.test_swarm_tokens_live import LiveApp

    class FastMarket(Market):
        calls = 0

        async def fetch_markets(self, tokens):
            self.calls += 1
            return {row['id']: dict(state='ok', price_usd=7.5,
                                   market_pool='pool', market_source='fixture')
                    for row in tokens}

    market = FastMarket()
    manager = SwarmTokensManager(Source(), client=Pages(rows()[:3]),
                                market=market, clock=lambda: 1000)
    manager._catalogue = rows()[:3]
    manager._complete, manager._cat_as_of, manager._cat_attempt = True, 1000, 1000
    app = LiveApp(manager)
    try:
        async with app.run_test(size=(149, 45)) as pilot:
            await app.workers.wait_for_complete()
            await manager.wait_pending()
            assert not manager.is_loading()
            app.screen._tick_loading()
            await app.workers.wait_for_complete()
            app.screen._tick_loading()
            await pilot.pause()
            assert [row['price_usd'] for row in app.screen.snapshot['tokens']] == [7.5] * 3
            assert painted(app.screen).count('$7.5') == 3
            assert 'loading' not in painted(app.screen)
            assert market.calls == 1
    finally:
        await manager.close()


async def test_loading_is_visible_before_long_token_search():
    from tests.screens.test_swarm_tokens_live import LiveProvider, LiveApp
    provider = LiveProvider()
    provider.is_loading = lambda _view: True
    app = LiveApp(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        app.screen.search_query = 'BLACKOUT ' * 6
        app.screen._tick_loading()
        await pilot.pause()
        heading = next(row for row in painted(app.screen).splitlines() if 'ALL TOKENS' in row)
        assert 'loading' not in heading
        assert 'loading' in painted(app.screen).splitlines()[-1]


async def test_loading_is_visible_in_compact_swarm_title():
    from maxpane_dashboard.screens.surf import SurfScreen, SERVICE_NAMES
    from tests.screens.test_surf_screen import (
        _TrackingBlockingManager, _ThemedHarness, _worst_case_title_payload,
    )
    manager = _TrackingBlockingManager()
    manager.release.set()
    screen = SurfScreen(manager, poll_interval=3600)
    app = _ThemedHarness(screen)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.workers.wait_for_complete()
        screen._mode = 'swarm'
        screen._title_data = _worst_case_title_payload()
        screen._title_data.update(
            swarm_breaker={'tripped': True},
            swarm_services_up={name: False for name in SERVICE_NAMES},
            swarm_health_status='degraded',
            swarm_launch_rows=[{'verdict': {'state': 'mismatch'}}] * 3,
        )
        manager.entered.clear()
        manager.release.clear()
        screen.start_refresh()
        await manager.entered.wait()
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' not in painted(screen).splitlines()[0]
        assert 'loading' in painted(screen).splitlines()[-1]
        manager.release.set()
        await app.workers.wait_for_complete()


@pytest.mark.parametrize('mode', ['dashboard','launchpad','pool4','pool4_user','swarm','agent','board','work','oracles'])
async def test_all_surf_bodies_hide_missing_source_notices(mode):
    from maxpane_dashboard.screens.surf import SurfScreen
    from tests.screens.test_surf_screen import _FakeManager, _ThemedHarness, _all_none_payload
    screen = SurfScreen(_FakeManager(_all_none_payload()))
    screen._mode = mode
    app = _ThemedHarness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        text = painted(screen).lower()
        assert 'unavailable' not in text
        assert 'stale' not in text
        assert 'load failed' not in text
        assert 'loading' not in text


@pytest.mark.parametrize('mode,hero_name,projection,key,values', [
    ('pool4_user', 'SurfPool4RackHero', 'surf_pool4_hero', 'rate', {'imd': 7.964}),
    ('pool4', 'SurfProtocolHero', 'surf_protocol_hero', 'totals',
     {'burned': 47, 'rewarded': 0, 'fees': 0}),
])
@pytest.mark.parametrize('identity_field,new_identity', [
    ('pool4_network', 'SEPOLIA'),
    ('pool4_hook_addr', '0x' + '3' * 40),
    ('pool4_token_addr', '0x' + '4' * 40),
])
async def test_pool4_cards_retain_failed_reads_only_for_the_same_deployment(
        mode, hero_name, projection, key, values, identity_field, new_identity):
    from maxpane_dashboard.screens.surf import SurfScreen
    from tests.screens.test_surf_screen import _FakeManager, _ThemedHarness, _all_none_payload
    from tests.widgets.test_card_loading import inset_rows

    payload = _all_none_payload()
    payload.update(pool4_network='MAINNET', pool4_hook_addr='0x' + '1' * 40,
                   pool4_token_addr='0x' + '2' * 40)
    payload[projection] = {key: dict(state='ok', read_ts=1000, **values)}
    manager = _FakeManager(payload)
    screen = SurfScreen(manager, poll_interval=3600)
    screen._mode = mode
    app = _ThemedHarness(screen)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        card = screen.query_one(hero_name).query_one('#hero-' + key)
        observed = inset_rows(app, card)
        assert any(row.strip() for row in observed)
        if key == 'totals':
            assert observed[0].split() == ['burned', '47']

        # A failure can omit addresses without identifying a different deployment.
        failed = dict(payload, pool4_hook_addr=None, pool4_token_addr=None)
        failed[projection] = {key: dict(state='unavailable', read_ts=None,
                                       **dict.fromkeys(values))}
        manager._payload = failed
        await screen._do_refresh()
        await pilot.pause()
        assert card.source_record.state == 'unavailable'
        assert inset_rows(app, card) == observed

        manager._payload = dict(failed, **{identity_field: new_identity})
        await screen._do_refresh()
        await pilot.pause()
        current = inset_rows(app, card)
        assert current != observed
        if key == 'rate':
            assert not any(row.strip() for row in current)
        else:
            assert current[0].split() == ['burned', '0']
        assert card.source_record.state == 'unavailable'


async def test_token_filter_cannot_retain_liquidity_from_the_previous_cohort():
    from textual.widgets import Select
    from tests.screens.test_swarm_tokens_live import LiveProvider, LiveApp
    from tests.widgets.test_card_loading import inset_rows

    provider = LiveProvider()
    now = provider.snapshot['as_of']
    rows = provider.snapshot['tokens'][:2]
    for row, chain, amount in zip(rows, ('eth', 'base'), (42, 0)):
        row.update(chain=chain, paired_symbol='IMD', paired_amount=amount,
                   liquidity_state='ok', liquidity_read_at=now)
    provider.snapshot['tokens'] = rows
    release, started = asyncio.Event(), asyncio.Event()
    release.set()
    fetch = provider.fetch_and_compute

    async def fetch_snapshot():
        started.set()
        await release.wait()
        return await fetch()

    provider.fetch_and_compute = fetch_snapshot
    app = LiveApp(provider)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        screen = app.screen
        card = screen.query_one('#hero-liquidity')
        assert inset_rows(app, card)[0].split() == ['42', 'IMD']

        for row in rows:
            row.update(paired_amount=None, liquidity_state='unavailable', liquidity_read_at=None)
        await screen._do_refresh()
        await pilot.pause()
        assert screen.snapshot['tokens_hero']['liquidity']['imd'] is None
        assert inset_rows(app, card)[0].split() == ['42', 'IMD']

        await pilot.press('f')
        screen.query_one('#filter-chain', Select).value = 'base'
        release.clear()
        started.clear()
        await pilot.click('#filter-apply')
        await started.wait()
        await pilot.pause()
        # The cached source must already use the new cohort while its read waits.
        assert screen.chain == 'base'
        assert inset_rows(app, card)[0].split() == ['0', 'IMD']
        release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert {row['chain'] for row in screen.snapshot['tokens']} == {'base'}
        assert screen.snapshot['tokens_hero']['liquidity']['imd'] is None
        assert inset_rows(app, card)[0].split() == ['0', 'IMD']


async def test_background_completion_during_refresh_is_not_lost():
    provider = Provider()
    provider.pending = True
    app = LoadingApp(provider)
    async with app.run_test() as pilot:
        screen = app.screen
        await provider.started.wait()
        screen._tick_loading()
        provider.pending = False
        screen._tick_loading()  # refresh still owns the worker
        provider.release.set()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await app.workers.wait_for_complete()
        screen._tick_loading()
        await pilot.pause()
        assert 'finished 43' in painted(screen)
        assert provider.reads == 1 and provider.projections == 2


async def test_cancelled_refresh_clears_spinner_and_can_reopen():
    provider = Provider()
    app = LoadingApp(provider)
    async with app.run_test() as pilot:
        screen = app.screen
        await provider.started.wait()
        screen._tick_loading()
        worker = next(w for w in app.workers if w.name == screen.REFRESH_WORKER_NAME)
        worker.cancel()
        await asyncio.gather(worker._task, return_exceptions=True)
        screen._tick_loading()
        await pilot.pause()
        assert 'loading' not in painted(screen)
        assert not screen._refresh_in_flight
        provider.release.set()
        screen.start_refresh()
        await app.workers.wait_for_complete()
        assert provider.reads == 2
