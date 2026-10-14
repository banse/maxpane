"""Production BOARD dispatch and sorting preserve the approved six-card hero."""
from maxpane_dashboard.data.surf_leaderboard_hero import project
from maxpane_dashboard.widgets.surf import SurfSwarmBoardHero, SurfSwarmLeaderboard, SurfNewsHero
from scripts.surf_leaderboard_hero_demo import MOCK_DATA
from tests.screens.test_surf_screen import _frozen_payload, _region_text, _surf_app


async def test_board_projection_reaches_six_cards_and_sorting_keeps_canonical_top():
    data = _frozen_payload(**MOCK_DATA)
    data['surf_leaderboard_hero'] = project(data=data, now=1000, sources={
        name: dict(state='ok', read_ts=990) for name in ('records', 'workers', 'contributors')})
    app = _surf_app(data)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.screen._do_refresh()
        await pilot.press('b')
        await pilot.pause()
        hero = app.screen.query_one(SurfSwarmBoardHero)
        assert hero.display and hero.size.height == 9
        cards = list(hero.children)
        assert len(cards) == 6 and {card.region.height for card in cards} == {9}
        for text in ('TOP SEAT', 'RECORDED', 'ACCEPT RATE', 'LAUNCHES', 'WORKERS', 'EFFORT',
                     '100k attempts', '4.18k accepted', '96k / 100k', '2,880', '500M',
                     'worked 2y 2w 6d'):
            assert text in _region_text(app, hero)
        before = _region_text(app, cards[0])
        app.screen.query_one(SurfSwarmLeaderboard).reverse_sort()
        await pilot.pause()
        assert _region_text(app, cards[0]) == before
        assert 'AGENT' in before and '99.9%' in before
        assert 'RANK 1' not in before
        await pilot.press('escape')
        await pilot.pause()
        assert app.screen.query_one(SurfNewsHero).display and not hero.display
        await pilot.press('b')
        await pilot.pause()
        assert hero.display and _region_text(app, cards[0]) == before
