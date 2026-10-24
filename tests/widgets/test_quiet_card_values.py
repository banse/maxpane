"""Observed card values survive reads; cold placeholders are quiet."""
from copy import deepcopy
from dataclasses import replace

from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.agent_rack_hero import AgentRackCard, agent_records
from maxpane_dashboard.widgets.swarm_tokens.hero import TokensHeroCard, token_records
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.widgets.test_card_loading import Cards, face


async def test_cold_card_fields_are_blank_or_zero_and_never_animate():
    records = [HeroRecord('center', 'CENTER', 'VALUE', '', digits='--'),
               HeroRecord('stats', 'STATS', 'VALUES', '', stats=(('jobs', '--'),), subtitle='--/-- known')]
    cards = [NewsHeroCard(record) for record in records]
    cards.append(AgentRackCard(next(r for r in agent_records(None) if r.key == 'runtime')))
    async with Cards(*cards).run_test(size=(80, 12)) as pilot:
        await pilot.pause()
        original = [face(pilot.app, card) for card in cards]
        assert 'jobs' in original[1] and '0/0 known' in original[1]
        assert cards[0].data.digits == ''
        assert all(value == '' for _, value in cards[2].data.stats)
        assert all('--' not in text and '◇' not in text and '<>' not in text for text in original)
        for frame in range(8):
            for card in cards:
                card.set_card_loading(True, frame)
            await pilot.pause()
            assert [face(pilot.app, card) for card in cards] == original


async def test_hero_retains_units_and_partial_counts_without_mutating_source():
    record = HeroRecord('volume', 'VOLUME', 'USD / 24H', '', digits='0.5', subtitle='5/12 known')
    card = NewsHeroCard(record)
    missing = replace(record, heading='kUSD / 24H', digits='--', subtitle='--/20 known', state='unavailable')
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_record(missing)
        await pilot.pause()
        assert '5/20 known' in face(pilot.app, card)
        assert 'USD / 24H' in face(pilot.app, card) and 'kUSD' not in face(pilot.app, card)
        assert card.data.digits == '0.5' and card.data.state == 'unavailable'
        assert missing.digits == '--' and missing.subtitle == '--/20 known'
        card.set_record(replace(record, digits='0', subtitle='0/20 known'))
        card.set_record(missing)
        await pilot.pause()
        assert card.data.digits == '0' and '0/20 known' in face(pilot.app, card)
        await pilot.resize_terminal(25, 12)
        assert card.data.digits == '0' and card.data.heading == record.heading


async def test_real_empty_body_supersedes_older_digits_and_prose_is_literal():
    card = NewsHeroCard(HeroRecord('accepted', 'ACCEPTED', 'WORK', '', digits='42'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        empty = replace(card.data, digits='', preview='no attempts', subtitle='')
        card.set_record(empty)
        card.set_record(replace(empty, digits='--', preview='', state='unavailable'))
        await pilot.pause()
        assert 'no attempts' in face(pilot.app, card) and card.data.digits == ''
        card.set_record(replace(empty, preview='A — B --flag -7'))
        card.set_card_loading(True, 4)
        await pilot.pause()
        assert 'A — B --flag -7' in face(pilot.app, card)


async def test_boardroom_remembers_body_and_footer_but_clears_on_scope_change():
    card = SurfboardCard('work', 'WIP', 0, 0)
    original = dict(primary='2', secondary='7 working', status='active',
                    work_summary={'workflows': 3}, meter_state='ok')
    card.set_data(original)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        missing = dict(original, primary='—', secondary='— working', status='loading', work_summary={'workflows': None})
        before = deepcopy(missing)
        card.set_data(missing)
        card.set_card_loading(True, 0)
        await pilot.pause()
        assert '7 working' in face(pilot.app, card) and '3 workflows' in face(pilot.app, card)
        assert missing == before and card.data['primary'] == '—'
        card.set_value_scope('other')
        card.set_data(missing)
        await pilot.pause()
        assert '0 working' in face(pilot.app, card) and '0 workflows' in face(pilot.app, card)
        assert '<>' not in face(pilot.app, card) and '◇' not in face(pilot.app, card)


async def test_token_liquidity_and_stats_use_retained_numeric_fields():
    payload = {'liquidity': {'state': 'ok', 'imd': 12, 'eth': 0, 'known': 3, 'total': 4}}
    record = next(r for r in token_records(payload) if r.key == 'liquidity')
    card = TokensHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_record(next(r for r in token_records(None) if r.key == 'liquidity'))
        await pilot.pause()
        assert '12 IMD' in face(pilot.app, card) and '0 ETH' in face(pilot.app, card)
        card.set_value_scope(('ETH', 'new filter'))
        card.set_record(next(r for r in token_records(None) if r.key == 'liquidity'))
        await pilot.pause()
        assert '0 IMD' in face(pilot.app, card) and '0 ETH' in face(pilot.app, card)


async def test_agent_runtime_owner_and_counts_retain_only_for_same_seat():
    from tests.widgets.test_surf_agent_rack_hero import Harness, payload, painted
    from maxpane_dashboard.widgets.surf.agent_rack_hero import SurfSwarmAgentRackHero
    data = payload()
    async with Harness(data).run_test(size=(149, 24)) as pilot:
        rack = pilot.app.query_one(SurfSwarmAgentRackHero)
        cold = {'seat': dict(data['seat']), 'owner': {'state': 'unavailable'}}
        rack.update_data(surf_agent_hero=cold)
        await pilot.pause()
        assert 'example.eth' in painted(pilot.app, 'owner')
        assert 'codex' in painted(pilot.app, 'runtime') and '1.2.3' in painted(pilot.app, 'runtime')
        assert '96%' in painted(pilot.app, 'accepted')
        # Changing the identity must discard every observation, including links.
        cold['seat']['token_id'] = 421
        rack.update_data(surf_agent_hero=cold)
        await pilot.pause()
        assert 'example.eth' not in painted(pilot.app, 'owner')
        assert 'codex' not in painted(pilot.app, 'runtime')
        assert '0%' in painted(pilot.app, 'accepted')
        assert not rack.query_one('#hero-owner').owner_text.spans


async def test_boardroom_seat_reset_and_real_empty_token_list():
    seat = SurfboardCard('agent', 'AGENT', 2, 0)
    seat.set_data(dict(token_id=3, primary='3', secondary='2 of 4', status='working'))
    tokens = SurfboardCard('swarm-tokens', 'TOKENS', 1, 5)
    tokens.set_data(dict(token_ranking={'latest': [{'id': 'a', 'symbol': 'FIRST', 'age_s': 60}]}))
    async with Cards(seat, tokens).run_test(size=(60, 12)) as pilot:
        seat.set_data(dict(token_id=3, primary='3', secondary='— of —', status='loading'))
        tokens.set_data(dict(token_ranking={'latest': None}))
        await pilot.pause()
        assert '2 of 4' in face(pilot.app, seat) and 'FIRST' in face(pilot.app, tokens)
        seat.set_data(dict(token_id=4, primary='4', secondary='— of —', status='loading'))
        tokens.set_data(dict(token_ranking={'latest': []}))
        await pilot.pause()
        assert '0 of 0' in face(pilot.app, seat)
        assert 'FIRST' not in face(pilot.app, tokens) and 'no launches' in face(pilot.app, tokens)


async def test_top_seat_change_cannot_inherit_the_old_leaders_stats():
    from maxpane_dashboard.widgets.surf.swarm_board_hero import BoardHeroCard
    record = HeroRecord('top', 'TOP SEAT', 'AGENT', '42 accepted', digits='527', subtitle='80%')
    card = BoardHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_record(replace(record, digits='600', footer='-- accepted', subtitle='--%'))
        await pilot.pause()
        assert '0 accepted' in face(pilot.app, card) and '0%' in face(pilot.app, card)
        assert '42 accepted' not in face(pilot.app, card) and '80%' not in face(pilot.app, card)


async def test_explicit_empty_boardroom_primary_clears_the_previous_observation():
    card = SurfboardCard('work', 'WIP', 0, 0)
    card.set_data(dict(primary='12', status='active'))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_data(dict(primary='', status='idle'))
        await pilot.pause()
        rows = face(pilot.app, card).splitlines()
        top = next(i for i, row in enumerate(rows) if '┌' in row)
        assert all(not row.strip('│ ') for row in rows[top+1:top+4])
        card.set_data(dict(primary='—', status='loading'))
        await pilot.pause()
        assert card._display_data['primary'] == ''


async def test_market_caption_keeps_its_observed_change_when_factory_shape_changes():
    from maxpane_dashboard.widgets.surf.news_hero import news_records
    record = next(r for r in news_records({'market': {'state': 'ok', 'price_usd': 1,
                       'change_24h_pct': 2}}) if r.key == 'market')
    card = NewsHeroCard(record)
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        missing = next(r for r in news_records(None) if r.key == 'market')
        card.set_record(missing)
        await pilot.pause()
        assert '+2.0% · 24h' in face(pilot.app, card)
        assert card.source_record.subtitle == '24h --'


async def test_latest_token_fields_retain_only_for_the_same_row_identity():
    card = SurfboardCard('swarm-tokens', 'TOKENS', 1, 5)
    card.set_data(dict(token_ranking={'latest': [{'id': 'ETH:one', 'symbol': 'FIRST', 'age_s': 60}]}))
    async with Cards(card).run_test(size=(30, 12)) as pilot:
        card.set_data(dict(token_ranking={'latest': [{'id': 'ETH:one', 'symbol': None, 'age_s': None}]}))
        await pilot.pause()
        assert 'FIRST' in face(pilot.app, card) and '60s' in face(pilot.app, card)
        card.set_data(dict(token_ranking={'latest': [{'id': 'ETH:two', 'symbol': None, 'age_s': None}]}))
        await pilot.pause()
        assert 'FIRST' not in face(pilot.app, card) and '60s' not in face(pilot.app, card)
