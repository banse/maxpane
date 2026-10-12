"""Selected POOL4 proposal 1, verified through the real Textual compositor."""
from dataclasses import replace

import pytest
from rich.color import Color

from scripts.surf_pool4_hero_demo import MOCK_CARDS, MOCK_DATA, SurfPool4HeroDemo
from maxpane_dashboard.analytics.surf_pool4_depth import band_distance_pct
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def refuse(*args, **kwargs):
        raise AssertionError("the POOL4 mockup must not request live data")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


async def test_balanced_pool4_heroes_fit_above_native_panels_at_owner_size():
    async with SurfPool4HeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "IMD PRICE", "sIMD RATE", "STAKING", "VAULT", "DOWNSIDE BID", "DRIP QUEUE"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(a.region.right < b.region.x for a, b in zip(cards, cards[1:]))
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        assert app.query_one("#pool4-body").region.y > cards[0].region.bottom
        assert app.query_one("#market-bottom").region.bottom <= app.query_one("#demo-footer").region.y
        viewport = app.query_one("#viewport")
        assert not viewport.max_scroll_x and not viewport.max_scroll_y
        for card in cards:
            text = painted(app, card)
            assert f"⊙ {card.data.title}" in text
            assert card.data.heading in text and card.data.footer in text
            assert all(corner in text for corner in "┌┐└┘")
            if card.data.subtitle:
                assert card.data.subtitle in text
        for index, label, value in (
            (3, "IMD", "82.4k"), (3, "sIMD", "10.35k"), (3, "addresses", "126"),
            (5, "queued", "7.44k IMD"), (5, "cap", "1.2k IMD/d"), (5, "queue", "6.2d"),
        ):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        for index in (0, 1, 2, 4):
            text = painted(app, cards[index])
            assert "╭" in text and "╯" in text  # Native large numeric faces.
        strips = app.screen._compositor.render_strips()
        inset = next(strip.crop(cards[0].region.x, cards[0].region.right)
                     for strip in strips if " USD " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        assert "MOCK DATA" in painted(app, app.query_one("#demo-title"))
        assert "MOCK DATA" in painted(app, app.query_one("#demo-footer"))
        body = painted(app, app.query_one("#pool4-body"))
        for text in ("POOL4 FLOW", "BURN & SUPPLY", "SIGNALS", "STAKERS", "IF IMD FALLS",
                     "3.20%", "18.60 ETH", "6.2d", "126", "top 3 = 38%"):
            assert text in body
        assert "unavailable" not in body and "Loading" not in body


async def test_narrow_resize_preserves_six_cards_and_can_scroll_to_last():
    changed = replace(MOCK_CARDS[5], stats=(("queued", "0 IMD"), ("cap", "1.2k IMD/d"), ("queue", "0d")))
    async with SurfPool4HeroDemo(cards=MOCK_CARDS[:-1] + (changed,)).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "0 IMD" in painted(pilot.app, pilot.app.query_one("#hero-queue"))
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one("#viewport")
        assert viewport.max_scroll_x > 0 and viewport.max_scroll_y > 0
        assert len(pilot.app.query(NewsHeroCard)) == 6
        assert {card.region.height for card in pilot.app.query(NewsHeroCard)} == {9}
        viewport.scroll_to(x=viewport.max_scroll_x, y=0, animate=False)
        await pilot.pause()
        assert "DRIP QUEUE" in painted(pilot.app) and "RATE LIMITED" in painted(pilot.app)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.max_scroll_x and not viewport.max_scroll_y


def test_mock_figures_reconcile_and_require_six_cards():
    data = MOCK_DATA
    assert data["pool4_vault_assets"] / data["pool4_vault_shares"] == pytest.approx(7.964)
    assert data["pool4_backlog_imd"] / data["pool4_drip_per_day"] == pytest.approx(6.2)
    assert band_distance_pct(data["pool4_current_tick"], data["pool4_backstop_lower_tick"]) == pytest.approx(3.20, abs=.005)
    holders = data["pool4_stakers"]
    assert len(holders) == data["pool4_staker_count"] == 126
    assert sum(row["imd"] for row in holders) == pytest.approx(82400)
    assert sum(row["pct"] for row in holders[:3]) == pytest.approx(38.2)
    with pytest.raises(ValueError, match="six"):
        SurfPool4HeroDemo(cards=MOCK_CARDS[:-1])
