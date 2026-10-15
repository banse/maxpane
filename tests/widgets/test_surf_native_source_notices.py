"""Source failures stay internal; missing fields paint neutral placeholders."""
from importlib import import_module

import pytest
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, LocalSourceHeroCard, NewsHeroCard
from maxpane_dashboard.widgets.surf.pool4u_stakers import SurfPool4UStakers


def painted(app):
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


class Harness(App):
    def __init__(self, widget, payload=None):
        super().__init__()
        self.widget, self.payload = widget, payload
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield self.widget

    def on_mount(self):
        if self.payload is not None:
            self.widget.update_data(**self.payload)


@pytest.mark.parametrize("module, name", [
    ("activity", "SurfDevActivity"), ("feed", "SurfFeed"),
    ("market", "SurfMarket"), ("nft", "SurfNft"),
    ("hero", "SurfHero"), ("news_hero", "SurfNewsHero"),
    ("launchpad", "SurfLaunchpadCoins"), ("launchpad_activity", "SurfLaunchpadActivity"),
    ("launchpad_hero", "SurfLaunchpadHero"), ("burnkeepers", "SurfBurnkeepers"),
    ("pool4_flow", "SurfPool4Flow"), ("pool4_hatches", "SurfPool4Hatches"),
    ("pool4_hero", "SurfPool4RackHero"), ("pool4_ratchet", "SurfPool4Ratchet"),
    ("pool4_split", "SurfPool4Split"), ("pool4_vault", "SurfPool4Vault"),
    ("pool4u_burn", "SurfPool4UBurn"), ("pool4u_depth", "SurfPool4UDepth"),
    ("pool4u_hero", "SurfPool4UserHero"), ("pool4u_signals", "SurfPool4USignals"),
    ("pool4u_stakers", "SurfPool4UStakers"), ("protocol_hero", "SurfProtocolHero"),
])
async def test_unread_widgets_show_no_source_warning_or_false_loader(module, name):
    widget = getattr(import_module("maxpane_dashboard.widgets.surf." + module), name)()
    async with Harness(widget, {}).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app).lower()
        for notice in ("unavailable", "stale", "load failed", "waiting for data", "no read yet", "loading"):
            assert notice not in output
        for card in pilot.app.query(NewsHeroCard):
            assert "unavailable" not in str(card.tooltip)


@pytest.mark.parametrize("card_cls", [NewsHeroCard, LocalSourceHeroCard])
@pytest.mark.parametrize("state", ["stale", "unavailable"])
async def test_source_state_does_not_replace_metric_footer_or_leak_in_tooltip(card_cls, state):
    card = card_cls(HeroRecord("sample", "SAMPLE", "TOTAL", "7 accepted", stats=(("jobs", "7"),),
                               state=state, read_ts=1791774000.0))
    async with Harness(card).run_test(size=(32, 11)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert "7 accepted" in output and "jobs" in output
        assert "stale" not in output and "unavailable" not in output
        assert "stale" not in str(card.tooltip) and "unavailable" not in str(card.tooltip)
        assert "as of" in str(card.tooltip)


@pytest.mark.parametrize("state, loading", [("sweeping", True), ("pending", False), ("failed", False)])
async def test_staker_loader_requires_an_in_flight_sweep(state, loading):
    async with Harness(SurfPool4UStakers(), dict(pool4_stakers=None, pool4_stakers_state=state)).run_test(size=(90, 20)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert ("◌ loading" in output) is loading
        assert "unavailable" not in output and "⚠" not in output
