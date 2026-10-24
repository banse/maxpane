"""Card fallbacks stay static while the screen owns the loading animation."""
from dataclasses import replace

import pytest
from textual.app import App
from textual.containers import Horizontal

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


def inset_rows(app, card):
    lines = face(app, card).splitlines()
    top = next(index for index, line in enumerate(lines) if '┌' in line)
    left, right = lines[top].index('┌'), lines[top].index('┐')
    return [line[left + 1:right] for line in lines[top + 1:top + 4]]


def card_styles(app, card):
    return [app.screen.get_style_at(x, y)
            for y in range(card.region.y, card.region.bottom)
            for x in range(card.region.x, card.region.right)]


@pytest.mark.parametrize('theme', ['matrix', 'minimal'])
@pytest.mark.parametrize('missing', ['-', '--', '—'])
@pytest.mark.parametrize('field', ['digits', 'preview', 'stats'])
async def test_missing_values_use_static_blank_body_or_zero_stats(monkeypatch, missing, field, theme):
    monkeypatch.delenv('NO_COLOR', raising=False)
    content = ((('known', '0'), ('pending', missing)) if field == 'stats' else missing)
    card = NewsHeroCard(HeroRecord('test', 'TEST', 'VALUE', '',
                                   state='unavailable', **{field: content}))
    app = Cards(card)
    app.register_theme(THEMES[theme])
    app.theme = theme
    async with app.run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        body = inset_rows(app, card)
        if field == 'stats':
            assert body[0].split() == ['known', '0']
            assert body[1].split() == ['pending', '0']
        else:
            assert not any(row.strip() for row in body)
        original, styles = face(app, card), card_styles(app, card)
        for busy, frame in ((True, 0), (True, 2), (True, 4), (True, 7), (False, 0)):
            card.set_card_loading(busy, frame)
            await pilot.pause()
            assert face(app, card) == original
            assert card_styles(app, card) == styles
            assert '◇' not in original and '<>' not in original


@pytest.mark.parametrize('field', ['digits', 'boardroom', 'status'])
@pytest.mark.parametrize('width', [10, 16, 24])
async def test_never_observed_central_body_is_blank_at_small_widths(field, width):
    if field == 'boardroom':
        card = SurfboardCard('work', 'WIP', 0, 0)
        card.set_data(dict(status='loading', primary='—'))
    elif field == 'status':
        card = AgentRackCard(next(r for r in agent_records(None) if r.key == 'status'))
    else:
        card = NewsHeroCard(HeroRecord('test', 'TEST', 'VALUE', '', digits='--'))
    card.styles.width = width
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        assert not any(row.strip() for row in inset_rows(pilot.app, card))
        assert '◇' not in face(pilot.app, card) and '<>' not in face(pilot.app, card)


@pytest.mark.parametrize('digits,expected', [('0 0F --', '0 0F 0'), ('-- 0F 3', '0 0F 3')])
@pytest.mark.parametrize('width', [16, 24])
async def test_partially_observed_status_preserves_counts_and_defaults_missing_count(digits, expected, width):
    record = next(r for r in agent_records(None) if r.key == 'status')
    card = AgentRackCard(replace(record, digits=digits))
    card.styles.width = width
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        fallback = inset_rows(pilot.app, card)
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert inset_rows(pilot.app, card) == fallback
        card.set_record(replace(record, digits=expected))
        await pilot.pause()
        assert inset_rows(pilot.app, card) == fallback


async def test_observed_central_value_survives_missing_read_without_animation():
    record = HeroRecord('test', 'TEST', 'VALUE', '', digits='42', accent=False)
    card = NewsHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        observed = inset_rows(pilot.app, card)
        assert any(row.strip() for row in observed)
        card.set_record(replace(record, digits='--', state='unavailable'))
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert inset_rows(pilot.app, card) == observed


async def test_cached_values_prose_and_fully_loaded_cards_do_not_animate(monkeypatch):
    cards = [NewsHeroCard(HeroRecord(str(i), 'TEST', 'VALUE', '', **fields)) for i, fields in enumerate([
        dict(digits='0'), dict(digits='42'), dict(preview='A — B --flag -7'),
        dict(stats=(('TOKEN--X', '0'),)), dict(preview='—'),
    ])]
    async with Cards(*cards).run_test(size=(130, 12)) as pilot:
        await pilot.pause()
        original = [face(pilot.app, c) for c in cards]
        assert 'A — B --flag -7' in original[2] and 'TOKEN--X' in original[3]
        calls = []
        for card in cards:
            monkeypatch.setattr(card, 'refresh', lambda *a, **kw: calls.append(1))
            for frame in (0, 4):
                card.set_card_loading(True, frame)
        assert not calls
        assert [face(pilot.app, c) for c in cards] == original


async def test_unknown_status_body_is_blank_and_liquidity_amounts_are_zero():
    status = AgentRackCard(next(r for r in agent_records(None) if r.key == 'status'))
    liquidity = TokensHeroCard(next(r for r in token_records(None) if r.key == 'liquidity'))
    async with Cards(status, liquidity).run_test(size=(60, 12)) as pilot:
        status.set_card_loading(True, 4)
        liquidity.set_card_loading(True, 4)
        await pilot.pause()
        assert not any(row.strip() for row in inset_rows(pilot.app, status))
        rows = inset_rows(pilot.app, liquidity)
        assert rows[0].split() == ['0', 'IMD'] and rows[1].split() == ['0', 'ETH']
        assert '0/0 known' in face(pilot.app, liquidity)


@pytest.mark.parametrize('missing', ['-', '--', '—'])
@pytest.mark.parametrize('state', ['ok', 'stale'])
async def test_retained_literal_dash_posts_are_not_missing_values(missing, state):
    payload = {key: {'state': state, 'text': missing, 'read_ts': 123}
               for key in ('announcement', 'reply')}
    cards = [NewsHeroCard(record) for record in news_records(payload)
             if record.key in ('announcement', 'reply')]
    async with Cards(*cards).run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        for card in cards:
            assert any(row.strip() == missing for row in inset_rows(pilot.app, card))
        original = [face(pilot.app, card) for card in cards]
        for card in cards:
            card.set_card_loading(True, 4)
        await pilot.pause()
        assert [face(pilot.app, card) for card in cards] == original


async def test_runtime_unknown_text_fields_and_inner_footer_are_blank():
    card = AgentRackCard(next(r for r in agent_records(None) if r.key == 'runtime'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        assert [row.strip() for row in inset_rows(pilot.app, card)] == ['runtime', 'daemon', 'model']
        original, styles = face(pilot.app, card), card_styles(pilot.app, card)
        footer = next(row for row in original.splitlines() if '└' in row)
        assert '--' not in footer and '—' not in footer and '0' not in footer
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert face(pilot.app, card) == original
            assert card_styles(pilot.app, card) == styles


@pytest.mark.parametrize('key,extra', [
    ('work', {}), ('surf-nft', {}),
    ('board', {'fleet_summary': {'tokens': 0, 'jobs': None, 'capacity': None}}),
    ('swarm-tokens', {'token_ranking': {'latest': None}}),
    ('announce', {'primary': 'A — B --flag'}), ('agent', {}),
])
async def test_boardroom_cards_stay_static_and_keep_empty_seat_inputs(key, extra):
    card = SurfboardCard(key, key.upper(), 0, 0)
    card.set_data(dict(status='loading', primary='—') | extra)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(pilot.app, card)
        if key in ('work', 'surf-nft', 'swarm-tokens'):
            assert not any(row.strip() for row in inset_rows(pilot.app, card))
        elif key == 'board':
            assert [row.split() for row in inset_rows(pilot.app, card)] == [
                ['tokens', '0'], ['jobs', '0'], ['capacity', '0']]
        elif key == 'announce':
            assert 'A — B --flag' in original
        else:
            assert card.query_one('Input').display
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert face(pilot.app, card) == original
        assert '◇' not in original and '<>' not in original


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


@pytest.mark.parametrize('key,caption', [
    ('accepted', '0%'), ('models', '0%'), ('effort', '0 tokens'), ('rewards', '$0'),
    ('rank', 'of 0'), ('earnings', '0 new'),
])
async def test_agent_unread_numeric_captions_keep_units_with_zero_fallback(key, caption):
    card = AgentRackCard(next(r for r in agent_records(None) if r.key == key))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        footer = next(row for row in face(pilot.app, card).splitlines() if '└' in row)
        assert caption in footer


async def test_token_coverage_keeps_observed_count_and_defaults_unread_total_to_zero():
    record = next(r for r in token_records({'volume': {'state': 'partial', 'amount': 42,
                                                       'known': 3, 'total': None}}) if r.key == 'volume')
    card = TokensHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        assert '3/0 known' in face(pilot.app, card)


async def test_literal_captions_remain_prose_and_unread_dates_are_blank():
    cards = [NewsHeroCard(HeroRecord('prose', 'TEST', 'VALUE', '', subtitle='A — B --flag -7')),
             AgentRackCard(next(r for r in agent_records(None) if r.key == 'owner'))]
    async with Cards(*cards).run_test(size=(60, 12)) as pilot:
        await pilot.pause()
        original = [next(row for row in face(pilot.app, c).splitlines() if '└' in row) for c in cards]
        assert 'A — B --flag -7' in original[0]
        assert 'paired' not in original[1] and '--' not in original[1] and '0' not in original[1]
        for card in cards:
            card.set_card_loading(True, 4)
        await pilot.pause()
        assert [next(row for row in face(pilot.app, c).splitlines() if '└' in row) for c in cards] == original
