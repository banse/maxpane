"""Missing card values animate locally without hiding retained observations."""
from dataclasses import replace

import pytest
from textual.app import App
from textual.containers import Horizontal
from textual.color import Color

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard, news_records
from maxpane_dashboard.widgets.surf.agent_rack_hero import AgentRackCard, agent_records
from maxpane_dashboard.widgets.swarm_tokens.hero import TokensHeroCard, token_records
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard


class Cards(App):
    CSS = ('Horizontal {height: 9;} NewsHeroCard, SurfboardCard {width: 24; height: 9;}'
           'SurfboardCard {padding: 0 1; border: round $panel; background: $surface;}')

    def __init__(self, *cards):
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'

    def compose(self):
        with Horizontal():
            yield from self.cards


def face(app, card):
    return '\n'.join(s.crop(card.region.x, card.region.right).text
                     for s in app.screen._compositor.render_strips()[card.region.y:card.region.bottom])


@pytest.mark.parametrize('theme', ['matrix', 'minimal'])
@pytest.mark.parametrize('missing', ['-', '--', '—'])
@pytest.mark.parametrize('field', ['digits', 'preview', 'stats'])
async def test_missing_values_pulse_only_during_reads(monkeypatch, missing, field, theme):
    monkeypatch.delenv('NO_COLOR', raising=False)
    content = ((('known', '0'), ('pending', missing)) if field == 'stats' else missing)
    record = HeroRecord('test', 'TEST', 'VALUE', '', state='unavailable', **{field: content})
    card = NewsHeroCard(record)
    app = Cards(card)
    app.register_theme(THEMES[theme])
    app.theme = theme
    async with app.run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(pilot.app, card)
        assert '◇' not in original
        colors, positions = [], []
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            painted = face(pilot.app, card)
            assert '◇' in painted
            if field == 'stats':
                assert '0' in painted
            row, col = next((y, line.index('◇')) for y, line in enumerate(painted.splitlines()) if '◇' in line)
            positions.append((row, col))
            colors.append(pilot.app.screen.get_style_at(card.region.x+col, card.region.y+row).color)
        assert positions[0] == positions[1]
        assert [color.get_truecolor() for color in colors] == [
            Color.parse(pilot.app.get_css_variables()['background']).monochrome.rgb,
            Color.from_rich_color(card.rich_style.color).monochrome.rgb,
        ]
        card.set_card_loading(False, 0)
        await pilot.pause()
        assert face(pilot.app, card) == original
        card.set_card_loading(True, 0)
        card.set_record(replace(record, digits='42', preview='', stats=()))
        await pilot.pause()
        assert '◇' not in face(pilot.app, card)


@pytest.mark.parametrize('theme', ['matrix', 'minimal'])
@pytest.mark.parametrize('field', ['digits', 'preview', 'stats', 'subtitle', 'boardroom'])
async def test_loading_background_is_inverse_and_confined_to_indicator(monkeypatch, theme, field):
    monkeypatch.delenv('NO_COLOR', raising=False)
    if field == 'boardroom':
        card = SurfboardCard('work', 'WIP', 0, 0)
        card.set_data(dict(status='loading', primary='—'))
    else:
        content = (('pending', '--'),) if field == 'stats' else '--'
        card = NewsHeroCard(HeroRecord('test', 'TEST', 'VALUE', '',
                                      state='unavailable', **{field: content}))
    app = Cards(card)
    app.register_theme(THEMES[theme])
    app.theme = theme
    async with app.run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(app, card)
        dark = Color.parse(app.get_css_variables()['background']).monochrome
        light = Color.from_rich_color(card.rich_style.color, app.ansi_theme).monochrome
        backgrounds = []
        positions = []
        padded = field in ('digits', 'preview', 'boardroom')
        for fraction, frame in zip((0, .25, .5, .75, 1, .75, .5, .25), range(8)):
            card.set_card_loading(True, frame)
            await pilot.pause()
            painted = face(app, card)
            row, col = next((y, line.index('◇')) for y, line in enumerate(painted.splitlines())
                            if '◇' in line)
            positions.append((row, col))
            x, y = card.region.x + col, card.region.y + row
            style = app.screen.get_style_at(x, y)
            assert style.color.get_truecolor() == dark.blend(light, fraction).rgb
            assert style.bgcolor.get_truecolor() == dark.blend(light, 1 - fraction).rgb
            if padded:
                assert painted.splitlines()[row][col-1:col+2] == ' ◇ '
                for offset in (-1, 1):
                    assert app.screen.get_style_at(x + offset, y).bgcolor == style.bgcolor
            # The pulse must not leak through Text alignment into any other cell.
            backgrounds.append([
                app.screen.get_style_at(card.region.x + cx, card.region.y + cy).bgcolor
                for cy in range(card.region.height) for cx in range(card.region.width)
                if not (cy == row and abs(cx - col) <= int(padded))
            ])
        assert len(set(positions)) == 1
        assert all(frame == backgrounds[0] for frame in backgrounds[1:])
        card.set_card_loading(False, 0)
        await pilot.pause()
        assert face(app, card) == original
        assert app.screen.get_style_at(x, y).bgcolor.get_truecolor() == Color.parse(
            app.get_css_variables()['background']).rgb


async def test_cached_values_prose_and_fully_loaded_cards_do_not_animate(monkeypatch):
    cards = [NewsHeroCard(HeroRecord(str(i), 'TEST', 'VALUE', '', **fields)) for i, fields in enumerate([
        dict(digits='0'), dict(digits='42'), dict(preview='A — B --flag -7'),
        dict(stats=(('TOKEN--X', '0'),)), dict(preview='—'),
    ])]
    async with Cards(*cards).run_test(size=(130, 12)) as pilot:
        await pilot.pause()
        original = [face(pilot.app, c) for c in cards]
        for c in cards:
            c.set_card_loading(True, 0)
        await pilot.pause()
        calls = []
        for c in cards:
            monkeypatch.setattr(c, 'refresh', lambda *a, **kw: calls.append(1))
            c.set_card_loading(True, 4)
        assert not calls
        assert [face(pilot.app, c) for c in cards] == original


async def test_agent_status_counts_and_token_liquidity_use_same_indicator():
    status = AgentRackCard(next(r for r in agent_records(None) if r.key == 'status'))
    liquidity = TokensHeroCard(next(r for r in token_records(None) if r.key == 'liquidity'))
    async with Cards(status, liquidity).run_test(size=(60, 12)) as pilot:
        status.set_card_loading(True, 0)
        liquidity.set_card_loading(True, 0)
        await pilot.pause()
        assert face(pilot.app, status).count('◇') == 2
        assert '0F' in face(pilot.app, status)
        for row, line in enumerate(face(pilot.app, status).splitlines()):
            for col, char in enumerate(line):
                if char == '◇':
                    x, y = status.region.x + col, status.region.y + row
                    ink = pilot.app.screen.get_style_at(x, y).bgcolor
                    assert all(pilot.app.screen.get_style_at(x + offset, y).bgcolor == ink
                               for offset in (-1, 1))
        assert face(pilot.app, liquidity).count('◇') == 4
        assert 'IMD' in face(pilot.app, liquidity) and 'ETH' in face(pilot.app, liquidity)


@pytest.mark.parametrize('missing', ['-', '--', '—'])
@pytest.mark.parametrize('state', ['ok', 'stale'])
async def test_retained_literal_dash_posts_are_not_missing_values(missing, state):
    payload = {key: {'state': state, 'text': missing, 'read_ts': 123}
               for key in ('announcement', 'reply')}
    cards = [NewsHeroCard(record) for record in news_records(payload)
             if record.key in ('announcement', 'reply')]
    async with Cards(*cards).run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        original = [face(pilot.app, c) for c in cards]
        for card in cards:
            card.set_card_loading(True, 0)
        await pilot.pause()
        assert [face(pilot.app, c) for c in cards] == original


async def test_runtime_unknown_inner_footer_pulses_with_missing_stats():
    record = next(r for r in agent_records(None) if r.key == 'runtime')
    card = AgentRackCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(pilot.app, card)
        card.set_card_loading(True, 0)
        await pilot.pause()
        text = face(pilot.app, card)
        assert text.count('◇') == 4
        assert '◇' in next(row for row in text.splitlines() if '└' in row)
        card.set_card_loading(False, 0)
        await pilot.pause()
        assert face(pilot.app, card) == original


@pytest.mark.parametrize('key,extra,expected', [
    ('work', {}, 1), ('surf-nft', {}, 1),
    ('board', {'fleet_summary': {'tokens': 0, 'jobs': None, 'capacity': None}}, 3),
    ('swarm-tokens', {'token_ranking': {'latest': None}}, 1),
    ('announce', {'primary': 'A — B --flag'}, 0),
    ('agent', {}, 0),
])
async def test_boardroom_obeys_card_state_and_keeps_empty_seats(key, extra, expected):
    card = SurfboardCard(key, key.upper(), 0, 0)
    card.set_data(dict(status='loading', primary='—', **{k:v for k,v in extra.items() if k != 'primary'}))
    if 'primary' in extra:
        card.set_data(dict(status='loading', **extra))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 0)
        await pilot.pause()
        assert face(pilot.app, card).count('◇') == expected
        if key == 'agent':
            assert card.query_one('Input').display
        card.set_data(dict(card.data, status='unavailable'))
        card.set_card_loading(True, 4)
        await pilot.pause()
        assert '◇' not in face(pilot.app, card)


async def test_loaded_wip_primary_keeps_static_zero_inner_and_outer_counts():
    card = SurfboardCard('work', 'WIP', 0, 0)
    card.set_data(dict(status='active', primary='2', secondary='— working',
                       work_summary={'workflows': None}, meter_state='ok'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(pilot.app, card)
        assert '0 working' in original and '0 workflows' in original
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert face(pilot.app, card) == original
        card.set_data(dict(card.data, secondary='7 working', work_summary={'workflows': 3}))
        await pilot.pause()
        assert '7 working' in face(pilot.app, card) and '3 workflows' in face(pilot.app, card)
        assert '◇' not in face(pilot.app, card)


@pytest.mark.parametrize('key,caption', [
    ('accepted', '◇%'), ('models', '◇%'), ('effort', '0 tokens'), ('rewards', '$◇'),
    ('rank', 'of ◇'), ('earnings', '0 new'),
])
async def test_agent_numeric_captions_keep_units_while_loading(key, caption):
    card = AgentRackCard(next(r for r in agent_records(None) if r.key == key))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 0)
        await pilot.pause()
        footer = next(row for row in face(pilot.app, card).splitlines() if '└' in row)
        assert caption in footer


async def test_token_coverage_keeps_known_count_during_loading():
    record = next(r for r in token_records({'volume': {'state': 'partial', 'amount': 42,
                                                       'known': 3, 'total': None}}) if r.key == 'volume')
    card = TokensHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 0)
        await pilot.pause()
        assert '3/◇ known' in face(pilot.app, card)


async def test_literal_captions_and_dates_are_not_numeric_fields():
    cards = [NewsHeroCard(HeroRecord('prose', 'TEST', 'VALUE', '', subtitle='A — B --flag -7')),
             AgentRackCard(next(r for r in agent_records(None) if r.key == 'owner'))]
    async with Cards(*cards).run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        original = [next(row for row in face(pilot.app, c).splitlines() if '└' in row) for c in cards]
        for card in cards:
            card.set_card_loading(True, 0)
        await pilot.pause()
        assert [next(row for row in face(pilot.app, c).splitlines() if '└' in row) for c in cards] == original
