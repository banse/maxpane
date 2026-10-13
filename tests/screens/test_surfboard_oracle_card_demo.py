"""The selected mock stays offline and paints the card in its proposed slot."""
from textual.widgets import Input

from scripts.surfboard_oracle_card_demo import OracleCardDemo, OracleMockCard
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.screens.test_surf_news_hero_demo import painted


async def test_oracle_preview_replaces_launchpad_without_io_or_saved_state(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError("mock preview must not read the network")

    def refuse_state(*args, **kwargs):
        raise AssertionError("mock preview must not touch config or cache")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)
    for target in ("maxpane_dashboard.config._read_config", "maxpane_dashboard.config._write_config",
                   "maxpane_dashboard.data.surf_cache.SurfCache.load", "maxpane_dashboard.data.surf_cache.SurfCache.save"):
        monkeypatch.setattr(target, refuse_state)
    async with OracleCardDemo().run_test(size=(149, 45)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        app = pilot.app
        card = app.screen.query_one(OracleMockCard)
        rendered = painted(app, card)
        assert all(word in rendered for word in ("ORACLES", "ASSESSING", "100 loaded", "86 attested"))
        assert "LAUNCHPAD" not in painted(app)
        assert "MOCK DATA" in painted(app)
        neighbors = list(app.screen.query(SurfboardCard))
        assert len(neighbors) == 12
        assert {item.region.height for item in neighbors} == {9}
        assert max(item.region.width for item in neighbors) - min(item.region.width for item in neighbors) <= 1
        assert card.region.x == app.screen.query_one("#surfboard-card-announce").region.x
        assert card.region.y == app.screen.query_one("#surfboard-card-protocol").region.y
        assert all(field.disabled for field in app.screen.query(Input))
        await pilot.click(card)
        await pilot.pause()
        assert app.screen.query_one(OracleMockCard) is card
