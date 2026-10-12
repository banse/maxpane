"""The selected LAUNCHPAD mock, composited without external I/O."""
import pytest
from rich.color import Color

from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from scripts.surf_launchpad_hero_demo import MOCK_CARDS, MOCK_DATA, MOCK_VOLUME, SurfLaunchpadHeroDemo
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))

    async def refuse(*args, **kwargs):
        raise AssertionError('the launchpad mock must not use network or clipboard')

    monkeypatch.setattr('httpx.AsyncClient.send', refuse)
    monkeypatch.setattr('maxpane_dashboard.clipboard.copy_text', refuse)

    def refuse_state(*args, **kwargs):
        raise AssertionError('the launchpad mock must not access user state')

    for target in ('maxpane_dashboard.config._read_config', 'maxpane_dashboard.config._write_config',
                   'maxpane_dashboard.data.surf_cache.SurfCache.load', 'maxpane_dashboard.data.surf_cache.SurfCache.save'):
        monkeypatch.setattr(target, refuse_state)


async def test_launchpad_mock_paints_six_equal_cards_and_native_context():
    async with SurfLaunchpadHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            'COINS', 'CURVE FLOW', 'VOLUME', 'CREATOR FEES', 'BURN QUEUE', 'BURNED']
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        assert all(a.region.right < b.region.x for a, b in zip(cards, cards[1:]))
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        for card in cards:
            output = painted(app, card)
            assert f'⊙ {card.data.title}' in output
            assert card.data.heading in output and card.data.footer in output
            assert all(corner in output for corner in '┌┐└┘')
            if card.data.subtitle:
                assert card.data.subtitle in output
        for index, label, value in ((1, 'swaps', '12.4k'), (1, 'traders', '486'), (1, 'creators', '64'),
                                    (4, 'accrued', '250'), (4, 'staged', '120'), (4, 'sendable', '120')):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        assert any(char in painted(app, cards[2]) for char in '▁▂▃▄▅▆▇█')
        # Literal glyph rows read from the compositor, including every fee digit.
        for index, glyphs in ((0, '╶─╮╶╮ ╭─╮'), (2, '╷ ╷╶─╮ ╭─╴'),
                              (3, '╭─╮ ╭─╮╭─╮╷ ╷╶─╮'), (5, '╶╮ ╭─╴ ╶─┐')):
            assert glyphs in painted(app, cards[index])
        assert '╰─╯•╰─╯╰─╯  ╵╰─╴' in painted(app, cards[3])
        strips = app.screen._compositor.render_strips()
        inset = next(strip.crop(cards[0].region.x, cards[0].region.right)
                     for strip in strips[cards[0].region.y:cards[0].region.bottom] if '┌' in strip.text)
        edge = next(segment for segment in inset if '┌' in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()['background'])
        assert edge.style.color == Color.parse(app.get_css_variables()['accent'])
        body = app.query_one('#launchpad-body')
        assert body.region.y > cards[0].region.bottom
        assert body.region.bottom < app.query_one('#demo-footer').region.y
        for label in ('LAUNCHPAD COINS', 'LAUNCHPAD ACTIVITY', 'CURVE FLOW', 'BURN PIPELINE', 'BURNKEEPERS',
                      '12400', '486', '0.0842', '250', '120', '15,700'):
            assert label in painted(app, body)
        for widget_id in ('#demo-title', '#demo-footer'):
            assert 'MOCK DATA' in painted(app, app.query_one(widget_id))
        viewport = app.query_one('#viewport')
        assert not viewport.max_scroll_x and not viewport.max_scroll_y


async def test_launchpad_mock_scrolls_and_recovers_on_resize():
    async with SurfLaunchpadHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one('#viewport')
        assert viewport.max_scroll_x > 0 and viewport.max_scroll_y > 0
        viewport.scroll_to(x=viewport.max_scroll_x, y=0, animate=False)
        await pilot.pause()
        assert 'BURNED' in painted(pilot.app) and 'EVENT TOTAL' in painted(pilot.app)
        viewport.scroll_to(y=viewport.max_scroll_y, animate=False)
        await pilot.pause()
        assert 'BURNKEEPERS' in painted(pilot.app)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.max_scroll_x and not viewport.max_scroll_y
        assert 'COINS' in painted(pilot.app) and 'BURNED' in painted(pilot.app)


def test_launchpad_mock_has_coherent_units_and_history():
    assert MOCK_DATA['coin_count'] == MOCK_DATA['launch_count'] == 210
    assert len(MOCK_DATA['coins']) <= 20 < MOCK_DATA['coin_count']
    assert MOCK_DATA['new_24h'] == 2 and MOCK_DATA['creator_count'] == 64
    assert MOCK_DATA['swap_count'] == 12400 and MOCK_DATA['trader_count'] == 486
    assert MOCK_DATA['creator_eth_owed'] == .0842
    assert MOCK_VOLUME['until'] - MOCK_VOLUME['since'] == 7200
    assert len(MOCK_VOLUME['eth']) == len(MOCK_VOLUME['usd']) == 8
    assert all(value >= 0 for value in MOCK_VOLUME['eth'])
    assert sum(MOCK_VOLUME['usd']) == 42600
    assert [value * MOCK_VOLUME['eth_usd'] for value in MOCK_VOLUME['eth']] == pytest.approx(MOCK_VOLUME['usd'])
    assert MOCK_CARDS[2].digits == '42.6' and MOCK_CARDS[2].points == tuple(MOCK_VOLUME['usd'])
    assert MOCK_CARDS[3].digits == '0.0842'
    assert MOCK_DATA['burn_bridgeable'] == 120 and MOCK_DATA['burn_ready'] is True
    assert sum(row['imd_burned'] for row in MOCK_DATA['launchpad_burnkeepers']) == MOCK_DATA['burned_total'] == 15700
    assert all(row['eth'] is None for row in MOCK_DATA['launchpad_activity'] if row['kind'] == 'launch')
    with pytest.raises(ValueError, match='six'):
        SurfLaunchpadHeroDemo(cards=MOCK_CARDS[:-1])
