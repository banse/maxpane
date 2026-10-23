"""Missing count captions display zero without changing source facts."""
from copy import deepcopy

import pytest

from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_board_hero import BoardHeroCard
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.widgets.test_card_loading import Cards, face


@pytest.mark.parametrize('key,caption,summary,expected', [
    ('announce', '', {'numerator': None, 'denominator': 11}, ('0 SIGNALS',)),
    ('work', '— working', {'work_summary': {'workflows': None}}, ('0 working', '0 workflows')),
    ('oracles', '-- agents', {'numerator': None}, ('0 agents', '0 chains')),
    ('surf-nft', '- building', {'nft_summary': {'building': None, 'mint_open': None}}, ('0 building', '0 build', '0 open')),
])
@pytest.mark.parametrize('status', ['loading', 'active', 'unavailable'])
async def test_boardroom_count_footers_are_zero_even_when_cold_or_busy(key, caption, summary, expected, status):
    payload = dict(status=status, primary='5', secondary=caption, **summary)
    original = deepcopy(payload)
    card = SurfboardCard(key, key.upper(), 0, 0)
    card.set_data(payload)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        for busy, frame in [(False, 0), (True, 0), (True, 4), (False, 4)]:
            card.set_card_loading(busy, frame)
            await pilot.pause()
            text = face(pilot.app, card)
            assert all(value in text for value in expected)
            assert '◇' not in text and 'loading' not in text
        assert payload == original


@pytest.mark.parametrize('key,label', [('work', 'working'), ('oracles', 'agents'), ('surf-nft', 'building')])
async def test_cold_bare_count_footer_gets_its_label_and_static_zero(key, label):
    card = SurfboardCard(key, key.upper(), 0, 0)
    card.set_data(dict(status='loading', primary='—', secondary='—'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        text = face(pilot.app, card)
        assert f'0 {label}' in text
        assert text.count('◇') == 1  # the main value only


async def test_count_only_missing_values_do_not_request_animation_redraws(monkeypatch):
    card = SurfboardCard('work', 'WIP', 0, 0)
    card.set_data(dict(status='active', primary='5', secondary='— working', work_summary={'workflows': None}))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        calls = []
        monkeypatch.setattr(card, 'refresh', lambda *args, **kwargs: calls.append(1))
        for frame in range(8):
            card.set_card_loading(True, frame)
        assert not calls
        assert not card._footer_has_missing_value


@pytest.mark.parametrize('cls', [NewsHeroCard, BoardHeroCard])
@pytest.mark.parametrize('missing', ['-', '--', '—'])
async def test_shared_hero_inner_and_outer_count_footers_keep_style_and_source(cls, missing):
    record = HeroRecord('count', 'TEST', 'VALUE', missing + ' attempts',
                        subtitle=missing + ' new /24h', digits='5', state='ok')
    card = cls(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        await pilot.pause()
        original = face(pilot.app, card)
        assert '0 attempts' in original and '0 new /24h' in original
        for frame in (0, 4):
            card.set_card_loading(True, frame)
            await pilot.pause()
            assert face(pilot.app, card) == original
        assert card.data == record


async def test_missing_primary_still_animates_above_a_static_zero_count():
    card = NewsHeroCard(HeroRecord('count', 'TEST', 'VALUE', '', subtitle='— cached', digits='—'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        text = face(pilot.app, card)
        assert '0 cached' in text and text.count('◇') == 1


async def test_compact_nft_footer_converts_counts_before_clipping():
    card = SurfboardCard('surf-nft', 'NFTS', 0, 0)
    card.set_data(dict(status='loading', primary='5', secondary='1 building', nft_summary={}))
    card.styles.width = 18
    async with Cards(card).run_test(size=(24, 12)) as pilot:
        card.set_card_loading(True, 4)
        await pilot.pause()
        text = face(pilot.app, card)
        assert '0bld · 0open' in text and '◇' not in text


@pytest.mark.parametrize('caption', ['A — B --flag -7', 'paired --', '--:--', '$--', '--%',
                                      '1 sIMD = — IMD', '--/-- known', 'note: -- tokens left in a quote', '5 agents', '0 workflows'])
def test_count_formatter_excludes_non_count_fields(caption):
    from rich.text import Text
    from maxpane_dashboard.widgets.card_inner import LoadingCard
    assert LoadingCard.count_caption(Text(caption)).plain == caption
