"""LAUNCHPAD rack integration, using the actual screen compositor."""
from maxpane_dashboard.widgets.surf.launchpad_hero import SurfLaunchpadHero
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_screen import _surf_app, _frozen_payload, _region_text
from tests.widgets.test_surf_launchpad_hero import payload

async def test_launchpad_rack_replaces_legacy_hero_and_updates_all_cards():
    data = _frozen_payload(surf_launchpad_hero=payload())
    async with _surf_app(payload=data).run_test(size=(149,45)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.press('l')
        hero = screen.query_one(SurfLaunchpadHero)
        assert hero.display
        assert sum(node.display for node in screen.query('.surf-hero')) == 1
        cards = list(hero.query(NewsHeroCard))
        assert len(cards) == 6
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        painted = _region_text(pilot.app, hero)
        for text in ('CREATOR FEES', '╰─╯•╰─╯╰─╯  ╵╰─╴', '2h to', 'READY', 'EVENT TOTAL'):
            assert text in painted
        assert screen.query_one('#surf-launchpad-body').display
        await pilot.press('escape')
        assert not hero.display
        await pilot.press('l')
        assert hero.display
        changed = payload()
        changed['queue']['ready'] = False
        changed['queue']['sendable'] = 0
        screen._data_manager._payload = dict(data, surf_launchpad_hero=changed)
        await screen._do_refresh()
        await pilot.pause()
        assert 'WAITING' in _region_text(pilot.app, hero)
