"""The selected news hero proposal, verified through the Textual compositor."""
from dataclasses import replace

import pytest
from rich.color import Color

from scripts.surf_news_hero_demo import MOCK_CARDS, NewsHeroCard, SurfNewsHeroDemo


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def refuse(*args, **kwargs):
        raise AssertionError("the mockup must not request live data")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


def painted(app, widget=None):
    strips = app.screen._compositor.render_strips()
    if widget is None:
        return "\n".join(strip.text for strip in strips)
    region = widget.region
    return "\n".join(strip.crop(region.x, region.right).text
                     for strip in strips[region.y:region.bottom])


async def test_six_rack_heroes_fit_above_the_news_body_at_owner_size():
    async with SurfNewsHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "ANNOUNCEMENT", "LATEST REPLY", "SIGNALS", "DEV ACTIVITY", "IMD MARKET", "NFT BOARDS"]
        assert len({card.region.y for card in cards}) == 1
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.x for card in cards}) == 6
        for left, right in zip(cards, cards[1:]):
            assert left.region.right < right.region.x
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        body = app.query_one("#news-body")
        assert body.region.y > cards[0].region.bottom
        assert app.query_one("#context-bottom").region.bottom < app.query_one("#demo-footer").region.y
        assert not app.query_one("#viewport").show_vertical_scrollbar
        assert not app.query_one("#viewport").show_horizontal_scrollbar
        assert "MOCK DATA" in painted(app) and "MOCK DATA" in painted(app, app.query_one("#demo-footer"))
        assert "ANNOUNCE FEED" in painted(app, body) and "DEV ACTIVITY" in painted(app, body)
        assert "IDENTITY.MD" in painted(app, app.query_one("#context-bottom"))
        assert "waiting for data" not in painted(app)
        for card in cards:
            output = painted(app, card)
            assert f"⊙ {card.data.title}" in output
            assert card.data.heading in output and card.data.footer in output
            assert all(edge in output for edge in "┌┐└┘")
        assert "KNOWN 11/11" in painted(app, cards[2])
        for label, count in (("fired", "2"), ("watch", "1"), ("quiet", "8")):
            assert any(label in line and count in line for line in painted(app, cards[2]).splitlines())
        for value in ("812", "1,967", "38"):
            assert value in painted(app, cards[5])
        assert "╭─╮ ╷ ╷╶╮" in painted(app, cards[4])
        assert "+2.3% · 24h" in painted(app, cards[4])
        strips = app.screen._compositor.render_strips()
        price = cards[4]
        inset = next(strip.crop(price.region.x, price.region.right)
                     for strip in strips[price.region.y:price.region.bottom] if " USD " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])


async def test_mock_record_replacement_and_resize_preserve_six_cards():
    changed = replace(MOCK_CARDS[2], stats=(("fired", "0"), ("watch", "0"), ("quiet", "11")))
    cards = MOCK_CARDS[:2] + (changed,) + MOCK_CARDS[3:]
    async with SurfNewsHeroDemo(cards=cards).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        signals = pilot.app.query_one("#hero-signals")
        assert any("quiet" in line and "11" in line for line in painted(pilot.app, signals).splitlines())
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert pilot.app.query_one("#viewport").show_horizontal_scrollbar
        assert len(pilot.app.query(NewsHeroCard)) == 6
        assert {card.region.height for card in pilot.app.query(NewsHeroCard)} == {9}
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not pilot.app.query_one("#viewport").show_horizontal_scrollbar
        assert "NFT BOARDS" in painted(pilot.app)


def test_mockup_requires_exactly_six_cards():
    with pytest.raises(ValueError, match="six"):
        SurfNewsHeroDemo(cards=MOCK_CARDS[:-1])
