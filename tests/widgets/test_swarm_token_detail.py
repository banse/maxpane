"""Selected-token widgets paint source-qualified facts and safe shared links."""
import inspect

import pytest
from rich.color import Color
from textual.app import App

from maxpane_dashboard.themes import THEMES
from tests.widgets.address_probe import icon_targets, link_targets


TOKEN_ADDRESS = '0x' + '1' * 40
POOL_ADDRESS = '0x' + '2' * 40
JOB = '29b90556-9f29-4ea1-8d61-e06fb4954ed0'


def payload():
    token = dict(symbol='DEMO', name='Demo Token', chain='eth', chain_id=1,
        token_address=TOKEN_ADDRESS, market_pool=POOL_ADDRESS, launch_pool=POOL_ADDRESS,
        price_usd=.00124, change_24h=12.4, mcap_usd=86800, fdv_usd=124000,
        volume_24h=18200, buys_24h=121, sells_24h=63, paired_amount=420,
        paired_symbol='IMD', token_amount=2400000, lp_state='two-sided', fee_pct=.3,
        withdrawn_pct=0, launch_id=1844, status='live', verdict='swarm',
        market_state='ok', market_read_at=1792076400, history_state='partial',
        history_read_at=1792076300, liquidity_state='ok', liquidity_read_at=1792076200,
        sparkline=[1, None, 3, 2, 4], market_source='geckoterminal')
    launch = dict(id='launch', number=1844, chain_id=1, status='live', verdict='swarm',
        objective='Build a community token.', recorded_ts=1792070000,
        repo_url='https://github.com/demo/token', site_label='demo',
        site_ens_name='demo.sites.imd.fun')
    contributors = [dict(seat=192, role='build', job_id=JOB, state='accepted', stage='contracts'),
                    dict(seat=192, role='review', job_id=JOB, state='accepted', stage='frontend'),
                    dict(seat=363, role='review', job_id=JOB, state='accepted', stage='contracts')]
    artifacts = [dict(kind='token', name='Demo Token', address=TOKEN_ADDRESS, chain_id=1),
                 dict(kind='site', name='demo', site_label='demo', site_ens_name='demo.sites.imd.fun')]
    sources = {key: dict(state='ok', read_ts=1792076000) for key in ('launch', 'contributors', 'artifacts')}
    return dict(token=token, launch=launch, contributors=contributors, artifacts=artifacts,
                sources=sources, is_mock=False)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError('widget tests must not use the network')
    monkeypatch.setattr('httpx.AsyncClient.send', refuse)


def harness(widget, data):
    class Probe(App):
        CSS = 'Screen {background: $background; color: $text;} DataTable {height: 1fr;}'
        def __init__(self):
            super().__init__()
            self.register_theme(THEMES['matrix'])
            self.theme = 'matrix'
        def compose(self):
            yield widget()
        def on_mount(self):
            self.query_one(widget).update_data(**data)
    return Probe()


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


def test_widget_contract_matches_frozen_model():
    from maxpane_dashboard.data.swarm_token_detail_models import WIDGET_SIGNATURES
    from maxpane_dashboard.widgets import swarm_token_detail as widgets
    expected = {
        'DetailHero': ('token', 'launch', 'contributors', 'sources', 'is_mock'),
        'LaunchSummary': ('token', 'launch', 'sources', 'is_mock'),
        'ContributorTable': ('contributors', 'sources'),
        'MarketPanel': ('token',), 'PositionPanel': ('token',),
        'ArtifactTable': ('token', 'artifacts', 'sources', 'is_mock'),
    }
    assert WIDGET_SIGNATURES == expected
    for name, keys in expected.items():
        assert tuple(inspect.signature(getattr(widgets, name).update_data).parameters)[1:] == keys


async def test_hero_six_cards_source_values_padding_and_palette():
    from maxpane_dashboard.widgets.swarm_token_detail import DetailHero
    from maxpane_dashboard.widgets.surf.news_hero import LocalSourceHeroCard
    data = payload()
    data.pop('artifacts')
    async with harness(DetailHero, data).run_test(size=(149, 11)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(LocalSourceHeroCard))
        assert [card.data.title for card in cards] == ['PRICE', 'MARKET CAP', 'VOLUME', 'LAUNCH', 'CONTRIBUTORS', 'POSITION']
        assert {card.region.height for card in cards} == {9}
        assert cards[4].data.digits == '2'  # Distinct seats, not contributing jobs.
        assert cards[0].data.digits == '.00124'
        assert '420 IMD' in painted(app) and 'two-sided' in painted(app)
        card = cards[5]
        lines = app.screen._compositor.render_strips()
        for y in range(card.region.y, card.region.bottom):
            row = lines[y].crop(card.region.x, card.region.right).text
            if '420' in row:
                left, right = row.index('│'), row.rindex('│')
                assert row[left + 1] == row[right - 1] == ' '
                style = app.screen.get_style_at(card.region.x + row.index('420'), y)
                assert style.color == Color.parse(app.get_css_variables()['foreground'])
                label = app.screen.get_style_at(card.region.x + row.index('paired'), y)
                assert label.color.get_truecolor() == app.ansi_theme.ansi_colors[2]
        assert 'market' in str(cards[0].tooltip).lower() or 'PRICE' in str(cards[0].tooltip)


@pytest.mark.parametrize('state', ['partial', 'stale'])
async def test_partial_contributors_are_lower_bound_and_unknown_is_not_zero(state):
    from maxpane_dashboard.widgets.swarm_token_detail import DetailHero
    data = payload()
    data.pop('artifacts')
    data['sources']['contributors'].update(state=state, partial=True)
    async with harness(DetailHero, data).run_test(size=(149, 11)) as pilot:
        await pilot.pause()
        card = pilot.app.query_one('#hero-token-contributors')
        assert card.data.digits == '≥2'
        assert 'stale' not in painted(pilot.app)
        data['contributors'] = None
        pilot.app.query_one(DetailHero).update_data(**data)
        await pilot.pause()
        assert card.data.digits == '--'
        data['contributors'] = []
        data['sources']['contributors'].update(state='ok', partial=False)
        pilot.app.query_one(DetailHero).update_data(**data)
        await pilot.pause()
        assert card.data.digits == '0'


async def test_launch_prose_addresses_site_links_and_markup_are_literal():
    from maxpane_dashboard.widgets.swarm_token_detail import LaunchSummary
    data = payload()
    data['launch']['objective'] = 'Build [red]DEMO[/] at ' + TOKEN_ADDRESS
    selected = {key: data[key] for key in ('token', 'launch', 'sources', 'is_mock')}
    async with harness(LaunchSummary, selected).run_test(size=(98, 12)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert '[red]DEMO[/]' in output and 'https://github.com/demo/token' in output
        assert TOKEN_ADDRESS in output
        assert TOKEN_ADDRESS in {item[2] for item in icon_targets(pilot.app)}
        links = link_targets(pilot.app)
        assert any(item[3:5] == ('address', TOKEN_ADDRESS) for item in links)
        assert any(item[3:5] == ('site', 'demo') for item in links)


async def test_long_objective_has_its_own_scroll_and_keeps_launch_metadata_visible():
    from maxpane_dashboard.widgets.swarm_token_detail import LaunchSummary
    data = payload()
    data['launch']['objective'] = 'Build ' + TOKEN_ADDRESS + ' ' + ('long objective ' * 500)
    selected = {key: data[key] for key in ('token', 'launch', 'sources', 'is_mock')}
    async with harness(LaunchSummary, selected).run_test(size=(98, 11)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert all(label in output for label in ('status', 'verdict', 'recorded', 'site', 'repository'))
        assert 'https://github.com/demo/token' in output
        assert pilot.app.query_one('.token-objective').max_scroll_y > 0
        assert TOKEN_ADDRESS in {item[2] for item in icon_targets(pilot.app)}


async def test_market_and_position_keep_separate_clocks_gaps_and_zero():
    from maxpane_dashboard.widgets.swarm_token_detail import MarketPanel, PositionPanel
    token = payload()['token']
    async with harness(MarketPanel, dict(token=token)).run_test(size=(49, 12)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert '$0.00124' in output and '+12.4%' in output and '121 / 63' in output
        assert 'buys / sells 121 / 63' in output and 'geckoterminal' in output
        assert 'history partial' in output
        assert POOL_ADDRESS in {item[2] for item in icon_targets(pilot.app)}
        assert 'selected indexed pool' in str(pilot.app.query_one(MarketPanel).tooltip)
    token.update(paired_amount=0, token_amount=None, liquidity_state='stale')
    async with harness(PositionPanel, dict(token=token)).run_test(size=(49, 10)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert 'stale' not in output and '0 IMD' in output and '0%' in output
        assert any('DEMO' in line and '--' in line for line in output.splitlines())


async def test_pool_identifier_is_a_fitted_hash_not_an_address():
    from maxpane_dashboard.widgets.swarm_token_detail import PositionPanel
    token = payload()['token']
    token['launch_pool'] = '0x' + 'a' * 64
    async with harness(PositionPanel, dict(token=token)).run_test(size=(49, 10)) as pilot:
        await pilot.pause()
        lines = painted(pilot.app).splitlines()
        row = next(index for index, line in enumerate(lines) if 'pool' in line)
        assert '…' in lines[row]
        assert not lines[row + 1].strip()
        assert not icon_targets(pilot.app)


@pytest.mark.parametrize('rows,state,expected', [(None, 'unavailable', '—'),
    ([], 'ok', 'No accepted contributors'), ([], 'partial', 'No contributors loaded')])
async def test_contributor_empty_states_are_honest(rows, state, expected):
    from maxpane_dashboard.widgets.swarm_token_detail import ContributorTable
    async with harness(ContributorTable, dict(contributors=rows,
        sources={'contributors': dict(state=state, read_ts=1792076000)})).run_test(size=(98, 12)) as pilot:
        await pilot.pause()
        assert expected in painted(pilot.app)


async def test_contributor_and_artifact_tables_use_safe_links_and_literal_text():
    from maxpane_dashboard.widgets.swarm_token_detail import ContributorTable, ArtifactTable
    data = payload()
    async with harness(ContributorTable, {key: data[key] for key in ('contributors', 'sources')}).run_test(size=(98, 12)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert '#192' in output and 'build' in output and 'accepted' in output
        assert any(item[3:5] == ('job', JOB) for item in link_targets(pilot.app))
    data['artifacts'][0]['name'] = '[/x]漢字\x1b\u202e demo'
    async with harness(ArtifactTable, {key: data[key] for key in ('token', 'artifacts', 'sources', 'is_mock')}).run_test(size=(149, 9)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert '[/x]漢字' in output and '\x1b' not in output and '\u202e' not in output
        assert TOKEN_ADDRESS in {item[2] for item in icon_targets(pilot.app)}
        assert any(item[3:5] == ('site', 'demo') for item in link_targets(pilot.app))


@pytest.mark.parametrize('state', ['stale', 'unavailable'])
async def test_source_warnings_are_hidden_but_cached_market_values_remain(state):
    from maxpane_dashboard.widgets.swarm_token_detail import MarketPanel
    token = payload()['token']
    token.update(market_state=state, history_state=state)
    async with harness(MarketPanel, dict(token=token)).run_test(size=(49, 12)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert state not in output
        assert state not in str(pilot.app.query_one(MarketPanel).tooltip)
        assert '$0.00124' in output
