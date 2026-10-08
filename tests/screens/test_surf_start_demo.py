"""Exercise the standalone mock rack as the user sees it."""

import pytest
from textual.widgets import Input

from scripts.surf_start_demo import DashboardCard, RackCard, SurfStartDemo


def painted(app, widget=None):
    strips = app.screen._compositor.render_strips()
    if widget is None:
        return "\n".join("".join(segment.text for segment in row) for row in strips)
    region = widget.region
    return "\n".join(
        "".join(segment.text for segment in strips[y].crop(region.x, region.right))
        for y in range(max(0, region.y), min(len(strips), region.bottom))
    )


@pytest.mark.parametrize("rows, slots, full_rows", [(4, 12, 1), (5, 18, 2)])
async def test_six_columns_and_central_terminal_span(rows, slots, full_rows):
    app = SurfStartDemo(rows=rows)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        cards = list(app.query(RackCard))
        assert len(cards) == slots
        assert sum(card.data is None for card in cards) == slots - 10
        first = cards[:6]
        assert len({card.region.x for card in first}) == 6
        assert len({card.region.y for card in first}) == 1
        assert len({card.region.y for card in cards}) == rows
        terminal = app.query_one("#terminal")
        assert terminal.region.x == first[1].region.x
        assert terminal.region.right == first[4].region.right
        assert terminal.region.y == cards[full_rows * 6].region.y
        assert terminal.region.bottom == cards[-1].region.bottom
        for card in cards[full_rows * 6:]:
            assert card.region.x in (first[0].region.x, first[-1].region.x)
            assert not card.region.overlaps(terminal.region)
        assert "MOCK DATA" in painted(app)
        assert "856 online" in painted(app, cards[1])
        assert "empty slot" in painted(app, cards[-1])
        assert app.query_one("#command").region.bottom < terminal.region.bottom
        viewport = app.query_one("#viewport")
        assert not viewport.show_horizontal_scrollbar
        assert not viewport.show_vertical_scrollbar
        for card in cards:
            assert card.region.bottom <= 44
            assert card.region.right <= 149
            assert "▱" in painted(app, card)
            if card.data:
                assert card.data.title in painted(app, card)
                assert card.data.primary in painted(app, card)
                assert card.data.secondary in painted(app, card)
        for card, title in zip(cards[7:10], ("SWARM TOKENS", "PORTFOLIO", "EARNINGS"), strict=True):
            assert card.data.title == title
            assert "○ planned" in painted(app, card)
            assert "coming soon" in painted(app, card)


async def test_variant_switch_and_mock_card_activation():
    app = SurfStartDemo(rows=5)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        assert len(app.query(RackCard)) == 12
        await pilot.click("#slot-02")
        await pilot.pause()
        assert "SWARM preview" in painted(app, app.query_one("#terminal"))
        await pilot.press("5")
        await pilot.pause()
        assert len(app.query(RackCard)) == 18
        await pilot.press("/")
        assert isinstance(app.focused, Input)
        await pilot.press("4", "5")
        assert app.query_one(Input).value == "45"
        assert len(app.query(RackCard)) == 18


async def test_replacement_mock_record_renders_without_layout_changes():
    card = DashboardCard("custom", "CUSTOM", "ready", "123 jobs", "42 pending", "LOAD", 3)
    app = SurfStartDemo(rows=4, cards=(card,))
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        first = app.query_one(RackCard)
        assert "CUSTOM" in painted(app, first)
        assert "123 jobs" in painted(app, first)
        assert "42 pending" in painted(app, first)
        assert len(app.query(RackCard)) == 12
        assert sum(widget.data is None for widget in app.query(RackCard)) == 11


async def test_terminal_commands_are_local_and_keyboard_preview_works():
    app = SurfStartDemo(rows=5)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        terminal = app.query_one("#terminal")
        assert "ANNOUNCE preview" in painted(app, terminal)
        await pilot.press("/")
        command = app.query_one(Input)
        for value, expected in (
            ("clear", None),
            ("help", "help / clear / reset"),
            ("echo hello", "Unknown demo command"),
            ("reset", "build a new dashboard"),
        ):
            command.value = value
            await pilot.press("enter")
            await pilot.pause()
            output = painted(app, terminal)
            if expected:
                assert expected in output
            else:
                assert "build a new dashboard" not in output
                assert "ANNOUNCE preview" not in output
        await pilot.press("escape")
        assert isinstance(app.focused, RackCard)
        await pilot.click("#four")
        await pilot.pause()
        assert len(app.query(RackCard)) == 12


def test_replacement_records_cannot_overflow_the_smaller_variant():
    card = DashboardCard("custom", "CUSTOM", "planned", "coming soon", "preview", "LOAD", 0)
    SurfStartDemo(rows=5, cards=(card,) * 12)
    with pytest.raises(ValueError, match="at most 12"):
        SurfStartDemo(rows=5, cards=(card,) * 13)


@pytest.mark.parametrize("rows", [4, 5])
async def test_small_terminal_scrolls_without_collapsing_the_grid(rows):
    app = SurfStartDemo(rows=rows)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        viewport = app.query_one("#viewport")
        assert viewport.show_horizontal_scrollbar
        assert viewport.show_vertical_scrollbar
        cards = list(app.query(RackCard))
        assert len({card.region.y for card in cards}) == rows
        assert len({card.region.x for card in cards[:6]}) == 6
        assert min(card.region.height for card in cards) >= 7
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.show_horizontal_scrollbar
        assert not viewport.show_vertical_scrollbar
        assert "95.9% accepted" in painted(app, cards[2])
