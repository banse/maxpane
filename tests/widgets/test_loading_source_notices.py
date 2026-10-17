"""Owned source placeholders stay neutral; third-party prose stays literal."""
from datetime import datetime
from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard.widgets.curator import (
    CuratorActivity, CuratorCleanList, CuratorCleanedList, CuratorClosestCalls,
    CuratorClusters, CuratorFilteredList, CuratorHero, CuratorLeaderboard,
    CuratorOperators, CuratorRawList, CuratorSegments, CuratorWalletLadder,
)
from maxpane_dashboard.widgets.fwa import (
    FWAActivityFeed, FWAChaseBoard, FWAHeroMetrics, FWAOddsBoard, FWASettlementTable,
    FWASignals,
)
from maxpane_dashboard.widgets.ev_table import EVTable
from maxpane_dashboard.widgets.panels import HeroRow
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.swarm_tokens import TokensTable
from maxpane_dashboard.widgets.ttt import TTTSignals
from tests.screens.test_fwa_screen import _frozen_payload as fwa_payload


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def compose(self):
        yield self.widget
        yield StatusBar()


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


CASES = [
    (TTTSignals, {}),
    (FWAHeroMetrics, {'price_available': False, 'crown_available': False}),
    (FWAOddsBoard, {'odds_available': False}),
    (FWAOddsBoard, {'odds_available': True, 'odds_stale': True, 'odds_as_of_block': 25,
                   'collection_odds': fwa_payload()['collection_odds']}),
    (FWAChaseBoard, {'chase_available': False}),
    (FWAActivityFeed, {'feed_available': False}),
    (FWASettlementTable, {'settle_available': False}),
    (CuratorHero, {}),
    (CuratorActivity, {}),
    (CuratorCleanList, {}),
    (CuratorCleanedList, {}),
    (CuratorClosestCalls, {}),
    (CuratorClusters, {}),
    (CuratorFilteredList, {}),
    (CuratorLeaderboard, {}),
    (CuratorOperators, {'analysis_as_of_hhmm': '12:34'}),
    (CuratorRawList, {}),
    (CuratorSegments, {}),
    (CuratorWalletLadder, {}),
    (TokensTable, {'tokens': None}),
    (EVTable, {'boost_rankings': [], 'attack_rankings': [], 'catalog_source': 'fallback'}),
]


@pytest.mark.parametrize('widget_type,kwargs', CASES, ids=[
    'shared-signals', 'fwa-hero', 'fwa-odds-missing', 'fwa-odds-old', 'fwa-chase',
    'fwa-feed', 'fwa-settlement', 'curator-hero', 'curator-activity',
    'curator-clean-analysis', 'curator-cleaned-list', 'curator-closest-calls',
    'curator-clusters', 'curator-filtered-list', 'curator-leaderboard',
    'curator-operators', 'curator-raw-list', 'curator-segments', 'curator-ladder',
    'tokens-table', 'bakery-catalogue',
])
async def test_owned_source_notices_are_neutral_during_refresh(widget_type, kwargs):
    widget = widget_type()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(**kwargs)
        app.query_one(StatusBar).set_loading(True)
        await pilot.pause()
        text = painted(app)
        assert 'loading' in text.splitlines()[-1]
        assert 'unavailable' not in text.casefold()
        assert 'stale' not in text.casefold()
        if kwargs.get('odds_stale'):
            assert 'block 25' in text
            assert widget._last_payload['odds_stale'] is True
        if kwargs.get('analysis_as_of_hhmm'):
            assert 'as of 12:34' in text


@pytest.mark.parametrize('reason', ['logs endpoint unavailable', 'refresh failed: RPC unavailable'])
async def test_fwa_internal_log_failure_is_neutral(reason):
    widget = FWAActivityFeed()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(feed_available=False, feed_unavailable_reason=reason)
        app.query_one(StatusBar).set_loading(True)
        await pilot.pause()
        text = painted(app)
        assert 'loading' in text.splitlines()[-1]
        assert 'unavailable' not in text.casefold()
        assert 'refresh failed' not in text
        assert widget._payload['reason'] == reason


async def test_failed_feed_keeps_real_event_prose_unchanged():
    widget = FWAActivityFeed()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(feed_available=True, draw_events=[{
            'ts': 1700000000, 'purchaser': '0x' + 'a' * 40,
            'collection': '0x' + 'b' * 40, 'collection_name': 'unavailable',
            'token_id': 1, 'outcome': 'kept', 'outcome_label': 'stale art retained',
        }])
        widget.update_data(feed_available=False, feed_unavailable_reason='logs endpoint unavailable')
        await pilot.pause()
        text = painted(app)
        assert 'unavailable' in text and 'stale art retained' in text
        assert 'logs endpoint unavailable' not in text


@pytest.mark.parametrize('name', [
    'pool_temp_signal', 'sellback_signal', 'buy_gate_signal',
    'emissions_signal', 'vrf_queue_signal', 'param_drift_signal',
])
async def test_fwa_computed_source_fallback_is_neutral_and_state_is_retained(name):
    from maxpane_dashboard.analytics import fwa_signals

    builder = getattr(fwa_signals, name)
    signal = (builder(None) if name == 'sellback_signal' else builder()).model_dump()
    assert 'unavailable' in signal['value_str']
    widget = FWASignals()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(**{name: signal})
        app.query_one(StatusBar).set_loading(True)
        await pilot.pause()
        text = painted(app)
        assert 'loading' in text.splitlines()[-1]
        assert 'unavailable' not in text
        assert '--' in text
        assert widget._payload[name] == signal


async def test_fwa_signal_domain_text_is_not_filtered():
    widget = FWASignals()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(buy_gate_signal={'value_str': 'GATED — unavailable to buyers', 'color': 'dim'})
        await pilot.pause()
        assert 'GATED — unavailable to buyers' in painted(app)


class FailedHero(HeroRow):
    BOXES = (('failed-value', 'VALUE'),)


def fail(*args):
    raise ValueError('unread')


async def test_shared_hero_failure_is_a_neutral_value():
    widget = FailedHero()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.render_box('#failed-value', 'VALUE', fail)
        await pilot.pause()
        text = painted(app)
        assert 'VALUE' in text and '—' in text
        assert 'unavailable' not in text


@pytest.mark.parametrize('kind', ['base', 'bakery'])
async def test_custom_signal_failure_is_a_neutral_value(kind, monkeypatch):
    if kind == 'base':
        from maxpane_dashboard.widgets.base.overview.bt_signals import BTSignals
        monkeypatch.setattr('maxpane_dashboard.widgets.base.overview.bt_signals._signal_indicator', fail)
        widget = BTSignals()
        update = widget.update_data
    else:
        from maxpane_dashboard.widgets.signals_panel import SignalsPanel
        widget = SignalsPanel()
        update = lambda: widget._signal_row('#sig-late-join', 'Late-Join EV', fail)
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        update()
        await pilot.pause()
        text = painted(app)
        assert '—' in text
        assert 'unavailable' not in text


@pytest.mark.parametrize('metrics', [None, {},
    {'agents_state': 'unavailable', 'agents_as_of': 1700000000},
    {'agents_state': 'stale', 'agents_as_of': 1700000000},
    {'agents_state': 'paused', 'agents_as_of': 1700000000},
])
async def test_portfolio_source_labels_keep_timestamps_and_operational_states(metrics):
    from maxpane_dashboard.widgets.portfolio import PortfolioHero

    # Isolate its existing four-box renderer from the separately tracked
    # Portfolio/TokensHero rack inheritance mismatch; exercise the real method.
    class PortfolioBoxes(HeroRow):
        DEFAULT_CSS = 'PortfolioBoxes > HeroBoxBase { width: 1fr; height: 7; }'
        BOXES = PortfolioHero.BOXES
        update_data = PortfolioHero.update_data

    widget = PortfolioBoxes()
    app = Harness(widget)
    async with app.run_test(size=(149, 45)) as pilot:
        widget.update_data(metrics)
        await pilot.pause()
        text = painted(app)
        assert 'unavailable' not in text and 'stale' not in text
        assert 'P/L' in text and '—' in text
        if metrics and metrics.get('agents_state'):
            stamp = datetime.fromtimestamp(metrics['agents_as_of']).strftime('%H:%M')
            assert f'as of {stamp}' in text
        if metrics and metrics.get('agents_state') == 'paused':
            assert 'paused' in text
