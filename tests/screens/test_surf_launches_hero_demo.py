"""The selected LAUNCHES market overview, checked through the compositor."""
from dataclasses import replace

import pytest
from rich.color import Color
from textual.widgets import DataTable

from scripts.surf_launches_hero_demo import MOCK_CARDS, MOCK_SNAPSHOT, NewsHeroCard, SurfLaunchesHeroDemo
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def refuse(*args, **kwargs):
        raise AssertionError("the LAUNCHES mockup must not request live data")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


async def test_market_overview_fits_above_native_panels_at_owner_size():
    async with SurfLaunchesHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "TOKENS", "VOLUME", "LIQUIDITY", "POOLS", "MOMENTUM", "TOP VOLUME"]
        assert len({card.region.y for card in cards}) == 1
        assert {card.region.height for card in cards} == {9}
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        for left, right in zip(cards, cards[1:]):
            assert left.region.right < right.region.x
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        body = app.query_one("#launches-body")
        assert body.region.y > cards[0].region.bottom
        assert body.region.bottom <= app.query_one("#demo-footer").region.y
        viewport = app.query_one("#viewport")
        assert not viewport.show_vertical_scrollbar and not viewport.show_horizontal_scrollbar
        assert "MOCK DATA" in painted(app, app.query_one("#demo-title"))
        assert "MOCK DATA" in painted(app, app.query_one("#demo-footer"))
        for card in cards:
            output = painted(app, card)
            assert f"⊙ {card.data.title}" in output
            assert card.data.heading in output and card.data.footer in output
            assert all(edge in output for edge in "┌┐└┘")
        for index, label, value in (
            (0, "tracked", "48"), (0, "new 24h", "4"), (0, "chains", "3"),
            (3, "two-sided", "35"), (3, "one-sided", "8"), (3, "unknown", "5"),
            (4, "rising", "22"), (4, "falling", "14"), (4, "flat", "5"),
            (5, "ORBIT", "$38.2k"), (5, "BMC", "$21.4k"), (5, "RNNN", "$14.8k"),
        ):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        assert "kUSD / 24H" in painted(app, cards[1]) and "41/48 known" in painted(app, cards[1])
        assert "╶╮ ╶─╮╷ ╷ ╭─╮" in painted(app, cards[1])  # native Digits: 124.8 thousand USD
        assert "≥12.4k IMD" in painted(app, cards[2]) and "≥3.8 ETH" in painted(app, cards[2])
        assert "43/48 known" in painted(app, cards[2]) and "41/48 known" in painted(app, cards[4])
        strips = app.screen._compositor.render_strips()
        tokens = cards[0]
        inset = next(strip.crop(tokens.region.x, tokens.region.right)
                     for strip in strips[tokens.region.y:tokens.region.bottom] if " STATS " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        body_text = painted(app, body)
        for label in ("ACTIVITY", "NEWLY LAUNCHED", "BEST PLAYS", "ALL TOKENS", "PAIRED LP", "PRICE 24H", "VERDICT"):
            assert label in body_text
        assert "ORBIT" in body_text and "BMC" in body_text and "RNNN" in body_text
        table = app.query_one(DataTable)
        assert table.row_count == 48 and not table.show_horizontal_scrollbar


async def test_resize_preserves_six_cards_and_exposes_overflow():
    changed = replace(MOCK_CARDS[0], stats=(("tracked", "12"), ("new 24h", "0"), ("chains", "1")))
    async with SurfLaunchesHeroDemo(cards=(changed,) + MOCK_CARDS[1:]).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert any("new 24h" in line and "0" in line for line in
                   painted(pilot.app, pilot.app.query_one("#hero-tokens")).splitlines())
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one("#viewport")
        assert viewport.show_horizontal_scrollbar and viewport.show_vertical_scrollbar
        assert len(pilot.app.query(NewsHeroCard)) == 6
        assert {card.region.height for card in pilot.app.query(NewsHeroCard)} == {9}
        viewport.scroll_to(x=viewport.max_scroll_x, y=0, animate=False)
        await pilot.pause()
        assert "TOP VOLUME" in painted(pilot.app)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.show_horizontal_scrollbar and not viewport.show_vertical_scrollbar
        assert "TOKENS" in painted(pilot.app) and "TOP VOLUME" in painted(pilot.app)


def test_fictional_body_and_hero_totals_agree():
    from maxpane_dashboard.analytics.swarm_tokens import project_snapshot

    data = project_snapshot(MOCK_SNAPSHOT)
    metrics = data["metrics"]
    assert (metrics["total"], metrics["new_24h"], metrics["volume_known"]) == (48, 4, 41)
    assert metrics["volume_24h"] == 124800
    assert (metrics["two_sided"], metrics["one_sided"], metrics["unknown"]) == (35, 8, 5)
    assert metrics["liquidity_imd"] == 12400 and metrics["liquidity_eth"] == 3.8
    assert metrics["liquidity_partial"] is True
    assert len(data["gainers"]) == 22 and len(data["losers"]) == 14
    assert sum(row["change_24h"] == 0 for row in data["tokens"]) == 5
    assert len({row["chain"] for row in data["tokens"]}) == 3
    assert [(row["symbol"], row["volume_24h"]) for row in data["tokens"][:3]] == [
        ("ORBIT", 38200), ("BMC", 21400), ("RNNN", 14800)]
    with pytest.raises(ValueError, match="six"):
        SurfLaunchesHeroDemo(cards=MOCK_CARDS[:-1])
