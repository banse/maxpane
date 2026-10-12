"""AGENT proposal four, composited offline with twelve coherent rack cards."""
from collections import Counter

import pytest
from rich.color import Color

from scripts.surf_agent_hero_demo import MOCK_CARDS, MOCK_DATA, SurfAgentHeroDemo
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_news_hero_demo import painted
from tests.widgets.address_probe import icon_targets, link_targets


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    async def refuse(*args, **kwargs):
        raise AssertionError('the mock must not use network or clipboard')
    monkeypatch.setattr('httpx.AsyncClient.send', refuse)
    monkeypatch.setattr('maxpane_dashboard.clipboard.copy_text', refuse)
    def refuse_state(*args, **kwargs):
        raise AssertionError('the mock must not access user state')
    for target in ('maxpane_dashboard.config._read_config', 'maxpane_dashboard.config._write_config',
                   'maxpane_dashboard.data.surf_cache.SurfCache.load', 'maxpane_dashboard.data.surf_cache.SurfCache.save'):
        monkeypatch.setattr(target, refuse_state)


async def test_agent_mock_has_two_rows_of_six_equal_cards_and_record():
    async with SurfAgentHeroDemo().run_test(size=(149,45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            'SEAT', 'ACCEPTED', 'EFFORT', 'REWARDS', 'RANK', 'STATUS',
            'OWNER', 'RUNTIME', 'MODELS', 'FEEDBACK', 'COLLAB', 'NODES']
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 2
        assert cards[6].region.y == cards[0].region.bottom + 1
        assert [card.region.x for card in cards[:6]] == [card.region.x for card in cards[6:]]
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        for start in (0,6):
            assert all(left.region.right < right.region.x for left,right in zip(cards[start:start+5],cards[start+1:start+6]))
        for card in cards:
            text = painted(app, card)
            assert card.data.title in text and card.data.heading in text
            assert card.data.subtitle in text
            assert all(corner in text for corner in '┌┐└┘')
        for key, needles in {
            'accepted': ('1,000 attempts', '96%', '▰', '▱'),
            'effort': ('HOURS', '1.8M tokens'),
            'rewards': ('$120.82', 'OWNER SHARE'),
            'rank': ('of 1,024',),
            'status': ('working', '2', 'capacity', '3', 'devices', 'BUSY', '▰'),
            'owner': ('example.eth', '⧉', 'paired 10-01'),
            'runtime': ('codex', 'vX.Y.Z', 'daemon', 'up to date'),
            'models': ('model A', 'high', 'model B', 'medium'),
            'feedback': ('sent', '186', 'submitted', '4', 'queued', '2'),
            'collab': ('collaborators', 'TOP #527 x84'),
            'nodes': ('review', '500', 'build', '340', 'oracle', '120'),
        }.items():
            text = painted(app, app.query_one(f'#hero-{key}'))
            assert all(needle in text for needle in needles), text
        # Literal glyphs prove that the chosen ID, counts and exact reward reach the compositor.
        assert '╷ ╷╶─╮╭─╮' in painted(app, cards[0])
        assert '╶╮ ╶─╮ ╭─╮╷ ╷' in painted(app, cards[3])
        segments = [segment for strip in app.screen._compositor.render_strips() for segment in strip]
        edge = next(segment for segment in segments if '┌' in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()['background'])
        assert edge.style.color == Color.parse(app.get_css_variables()['accent'])
        busy = app.query_one('#hero-status').region
        footer = app.screen._compositor.render_strips()[busy.bottom-1].crop(busy.x,busy.right)
        assert next(segment for segment in footer if 'BUSY' in segment.text).style.color.get_truecolor(app.ansi_theme) == app.ansi_theme.ansi_colors[3]
        assert all(segment.style.color.get_truecolor(app.ansi_theme) == app.ansi_theme.ansi_colors[2]
                   for segment in footer if '▰' in segment.text)
        body = app.query_one('#agent-record')
        assert body.region.y > cards[6].region.bottom
        assert body.region.bottom <= app.query_one('#demo-footer').region.y
        assert 'RECORD' in painted(app, body) and 'review' in painted(app, body)
        assert '1,000' in painted(app, body) or '960 older' in painted(app, body)
        assert all('MOCK DATA' in painted(app, app.query_one(key)) for key in ('#demo-title','#demo-footer'))
        assert not app.query_one('#viewport').max_scroll_x and not app.query_one('#viewport').max_scroll_y
        assert any(target[2] == MOCK_DATA['owner'] for target in icon_targets(app))
        assert any(target[4] == MOCK_DATA['owner'] for target in link_targets(app))


async def test_agent_mock_scrolls_and_recovers_on_resize():
    async with SurfAgentHeroDemo().run_test(size=(149,45)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(100,28)
        await pilot.pause()
        view = pilot.app.query_one('#viewport')
        assert view.max_scroll_x > 0 and view.max_scroll_y > 0
        view.scroll_to(x=view.max_scroll_x,y=0,animate=False)
        await pilot.pause()
        assert 'STATUS' in painted(pilot.app) and 'NODES' in painted(pilot.app)
        view.scroll_to(x=0,y=view.max_scroll_y,animate=False)
        await pilot.pause()
        assert 'RECORD' in painted(pilot.app)
        await pilot.resize_terminal(149,45)
        await pilot.pause()
        assert not view.max_scroll_x and not view.max_scroll_y
        assert 'SEAT' in painted(pilot.app) and 'OWNER' in painted(pilot.app)


def test_agent_mock_data_agrees_with_card_values_and_record():
    rows = MOCK_DATA['rows']
    assert len(rows) == MOCK_DATA['attempts'] == 1000
    assert Counter(row['work_status'] for row in rows) == dict(accepted=960,rejected=20,failed=10,pending=10)
    assert Counter(row['node_key'] for row in rows if row['work_status']=='accepted') == dict(
        adversarial_review=500,build_contract_project=340,oracle_assess=120)
    assert MOCK_DATA['accepted'] / MOCK_DATA['attempts'] == .96
    assert MOCK_DATA['wall_clock_s'] == 320*3600 and MOCK_DATA['output_tokens'] == 1800000
    assert MOCK_DATA['rewards_imd'] == pytest.approx(12.84)
    assert MOCK_DATA['rewards_imd'] * MOCK_DATA['imd_usd'] == pytest.approx(120.8244)
    assert MOCK_CARDS[3].digits == '12.84' and MOCK_CARDS[3].subtitle == '$120.82'
    assert MOCK_DATA['paired_ts'] <= min(row['submitted_ts'] for row in rows)
    with pytest.raises(ValueError,match='twelve'):
        SurfAgentHeroDemo(cards=MOCK_CARDS[:-1])
