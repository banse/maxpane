"""Approved SWARM proposal 2 as painted in the standalone mockup."""
from dataclasses import replace

import pytest
from rich.color import Color

from scripts.surf_swarm_hero_demo import MOCK_CARDS, NewsHeroCard, SurfSwarmHeroDemo
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def refuse(*args, **kwargs):
        raise AssertionError("the SWARM mockup must not request live data")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


async def test_balanced_heroes_fit_above_native_swarm_panels_at_owner_size():
    async with SurfSwarmHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "FLEET", "OUTPUT", "WORKFLOWS", "LAUNCHES", "LATEST WORKFLOW", "SITES"]
        assert len({card.region.y for card in cards}) == 1
        assert {card.region.height for card in cards} == {9}
        for left, right in zip(cards, cards[1:]):
            assert left.region.right < right.region.x
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        assert app.query_one("#swarm-body").region.y > cards[0].region.bottom
        assert app.query_one("SurfSwarmSites").region.bottom < app.query_one("#demo-footer").region.y
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
            (0, "online", "966"), (0, "working", "8"), (0, "enrolled", "1,972"),
            (1, "steps", "2,621"), (1, "jobs", "224"), (1, "oracles", "48"),
            (2, "completed", "142"), (2, "running", "4"), (2, "blocked", "3"),
            (3, "live", "47"), (3, "parked", "2"),
        ):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        assert "149 cached" in painted(app, cards[2]) and "49 cached" in painted(app, cards[3])
        assert "Build a shared" in painted(app, cards[4]) and "8m ago" in painted(app, cards[4])
        assert "named sites" in painted(app, cards[5])
        assert "╭─╴╶─╮" in painted(app, cards[5])  # native Digits 63
        strips = app.screen._compositor.render_strips()
        output = cards[1]
        footer = strips[output.region.bottom - 1].crop(output.region.x, output.region.right)
        assert any(any(char in segment.text for char in "▁▂▃▄▅▆▇█")
                   and segment.style.color.get_truecolor() == app.ansi_theme.ansi_colors[2]
                   for segment in footer)
        fleet = cards[0]
        inset = next(strip.crop(fleet.region.x, fleet.region.right)
                     for strip in strips[fleet.region.y:fleet.region.bottom] if " STATS " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        body = painted(app, app.query_one("#swarm-body"))
        for text in ("WORKFLOWS", "LATEST LAUNCHES", "LAUNCHES", "SITES", "completed", "$NOVA", "demo-review"):
            assert text in body
        assert "Loading" not in body and "unavailable" not in body


async def test_variant_data_and_resize_keep_all_six_cards_accessible():
    changed = replace(MOCK_CARDS[0], stats=(("online", "12"), ("working", "0"), ("enrolled", "40")))
    async with SurfSwarmHeroDemo(cards=(changed,) + MOCK_CARDS[1:]).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert any("working" in line and "0" in line for line in
                   painted(pilot.app, pilot.app.query_one("#hero-fleet")).splitlines())
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one("#viewport")
        assert viewport.show_horizontal_scrollbar and viewport.show_vertical_scrollbar
        assert len(pilot.app.query(NewsHeroCard)) == 6
        assert {card.region.height for card in pilot.app.query(NewsHeroCard)} == {9}
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.show_horizontal_scrollbar and not viewport.show_vertical_scrollbar
        assert "named sites" in painted(pilot.app)


def test_mockup_requires_exactly_six_cards():
    with pytest.raises(ValueError, match="six"):
        SurfSwarmHeroDemo(cards=MOCK_CARDS[:-1])
