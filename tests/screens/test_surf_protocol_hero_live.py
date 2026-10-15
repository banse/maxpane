"""The approved protocol overview uses the production projection and screen."""
from maxpane_dashboard.data.surf_protocol_hero import project
from maxpane_dashboard.widgets.surf.protocol_hero import SurfProtocolHero
from maxpane_dashboard.widgets.surf.launchpad_hero import SurfLaunchpadHero
from maxpane_dashboard.widgets.surf import SurfHero, SurfNewsHero, SurfPool4RackHero
from tests.screens.test_surf_screen import _surf_app, _mainnet_pool4_payload, _region_text


async def test_protocol_live_projection_replaces_only_protocol_hero():
    data = _mainnet_pool4_payload()
    data.update(pool4_total_burned=33300, pool4_total_rewarded=5876,
                pool4_total_fee_token=3800, pool4_backlog_imd=7440,
                pool4_drippable=250, pool4_drip_per_day=1200)
    data['surf_protocol_hero'] = project(
        data=data, sources={'pool4': dict(state='ok', read_ts=990)}, now=1000)
    app = _surf_app(data)
    async with app.run_test(size=(149, 45)) as pilot:
        await app.screen._do_refresh()
        await pilot.press('e')
        await pilot.pause()
        hero = app.screen.query_one(SurfProtocolHero)
        assert hero.display and hero.size.height == 9
        assert not app.screen.query_one(SurfHero).display
        pixels = _region_text(app, hero)
        for text in ('TOTALS', 'INVENTORY', 'REWARD SPLIT', 'UNSETTLED', 'DELIVERY', 'CHECKS',
                     'burned', 'rewarded', 'fees', '7.44k', '250', '1.2k/d'):
            assert text in pixels
        for key, cls in [('4', SurfPool4RackHero), ('l', SurfLaunchpadHero), ('escape', SurfNewsHero), ('e', SurfProtocolHero)]:
            await pilot.press(key)
            await pilot.pause()
            shown = [child for child in app.screen.query_one('#hero-row').children if child.display]
            assert len(shown) == 1 and isinstance(shown[0], cls)
