"""Approved POOL4 hero reaches the production screen from its projection."""
from maxpane_dashboard.data.surf_pool4_hero import project
from maxpane_dashboard.widgets.surf.pool4_hero import SurfPool4RackHero
from tests.screens.test_surf_screen import _surf_app, _mainnet_pool4_payload, _region_text

async def test_pool4_live_projection_replaces_only_market_hero():
    data=_mainnet_pool4_payload()
    data['pool4_share_price']=7.964
    data['pool4_backlog_imd']=7440
    data['pool4_drip_per_day']=1200
    data['pool4_backlog_days']=6.2
    data['surf_pool4_hero']=project(data=data,sources={key:dict(state='ok',read_ts=990) for key in ('pool4','market','stakers')},now=1000)
    app=_surf_app(data)
    async with app.run_test(size=(149,45)) as pilot:
        await app.screen._do_refresh()
        await pilot.press('4')
        await pilot.pause()
        hero=app.screen.query_one(SurfPool4RackHero)
        assert hero.display and hero.size.height == 9
        pixels=_region_text(app,hero)
        for label in ('IMD PRICE','sIMD RATE','STAKING','VAULT','DOWNSIDE BID','DRIP QUEUE','7.44k IMD','1.2k IMD/d','6.2d'):
            assert label in pixels
        assert hero.query_one('#hero-rate').data.digits == '7.964'
        await pilot.press('escape')
        await pilot.pause()
        assert not hero.display
