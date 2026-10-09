"""The approved rack is a fixed six-column machine faceplate, not a reflow."""
from textual.app import App
import pytest

from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard


class RackApp(App):
    def compose(self):
        yield SurfboardRack(id="rack")


def painted(app):
    return "\n".join("".join(segment.text for segment in strip)
                     for strip in app.screen._compositor.render_strips())


@pytest.mark.parametrize("key,status,ink", [
    ("agent", "active", 2), ("agent", "stale", 3),
    ("agent", "unavailable", 3), ("protocol", "active", 3),
    ("portfolio", "planned", None), ("bay-11", "unassigned", None),
])
async def test_status_colors_the_taller_inset_without_a_separate_status_row(key, status, ink):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key=key, status=status,
            primary="IDMD #420", secondary="95.9% accepted")])
        await pilot.pause()
        card = rack.query_one(f"#surfboard-card-{key}", SurfboardCard)
        strips = [strip.crop(card.region.x, card.region.right) for strip in
                  pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
        lines = [strip.text for strip in strips]
        assert not any(label in "\n".join(lines) for label in
                       ("active", "stale", "unavailable", "experimental", "planned", "unassigned"))
        top = next(i for i, line in enumerate(lines) if "┌" in line)
        left, right = lines[top].index("┌"), lines[top].index("┐")
        assert lines[top + 1][left:right + 1] == "│" + " " * (right - left - 1) + "│"
        assert card.data["primary"] in lines[top + 2]
        assert card.data["secondary"] in lines[top + 3]
        assert lines[top + 4][left:right + 1] == "└" + "─" * (right - left - 1) + "┘"
        border = next(segment for segment in strips[top] if "┌" in segment.text)
        expected = pilot.app.ansi_theme.ansi_colors[ink] if ink is not None else border.style.color.get_truecolor()
        if ink is None:
            assert expected.red == expected.green == expected.blue < 200
        for strip in strips[top:top + 5]:
            for segment in strip.crop(left, right + 1):
                if any(char in "┌┐└┘─│" for char in segment.text):
                    assert segment.style.color.get_truecolor() == expected


@pytest.mark.parametrize("size", [(149, 45), (140, 36)])
@pytest.mark.parametrize("primary,expected", [
    ("894 online", ["╭─╮╭─╮╷ ╷", "├─┤╰─┤╰─┤", "╰─╯╶─╯  ╵"]),
    ("0 online", ["╭─╮", "│ │", "╰─╯"]),
    ("1,000 online", ["╶╮ ╭─╮╭─╮╭─╮", " │ │ ││ ││ │", "╶┴╴╰─╯╰─╯╰─╯"]),
    ("12,345 online", ["╶╮ ╶─╮╶─╮╷ ╷╭─╴", " │ ┌─┘ ─┤╰─┤╰─╮", "╶┴╴╰─╴╶─╯  ╵╶─╯"]),
    ("1,234,567 online", ["", "1,234,567", ""]),
    ("unavailable", ["", "unavailable", ""]),
])
async def test_swarm_inset_labels_and_centers_native_digits_or_whole_fallback(size, primary, expected):
    async with RackApp().run_test(size=size) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="swarm", status="stale", primary=primary,
            secondary="27 working", meter_kind="sparkline", points=[0, 1, 2, 3, 4, 5, 6, 7])])
        await pilot.pause()
        card = rack.query_one("#surfboard-card-swarm", SurfboardCard)
        strips = [strip.crop(card.region.x, card.region.right) for strip in
                  pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
        top = next(i for i, strip in enumerate(strips) if "┌" in strip.text)
        left, right = strips[top].text.index("┌"), strips[top].text.index("┐")
        assert " AGENTS ONLINE " in strips[top].text
        assert strips[top + 4].text[left:right + 1] == "└" + " 27 working ".center(right - left - 1, "─") + "┘"
        for strip, row in zip(strips[top + 1:top + 4], expected):
            padding = (right - left - 1 - len(row)) // 2
            assert strip.text[left + 1:right] == (" " * padding + row).ljust(right - left - 1)
        footer = next(segment for segment in strips[top + 4] if "27 working" in segment.text)
        assert not footer.style.bold
        assert footer.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[3]
        assert "24H ▁▂▃▄▅▆▇█" in "\n".join(strip.text for strip in strips)
        header = next(segment for segment in strips[top] if "AGENTS ONLINE" in segment.text)
        assert header.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[3]


async def test_four_rows_and_twelve_slots_keep_terminal_in_middle_three_rows():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data()
        await pilot.pause()
        cards = list(rack.query(SurfboardCard))
        terminal = rack.query_one(SurfboardTerminal)
        assert len(cards) == 12
        assert len({card.region.y for card in cards}) == 4
        assert len({card.region.y for card in cards[:6]}) == 1
        assert cards[6].region.y == terminal.region.y == cards[7].region.y
        assert terminal.region.bottom == cards[10].region.bottom == cards[11].region.bottom
        assert terminal.region.x > cards[6].region.x
        assert terminal.region.right < cards[7].region.x
        text = painted(pilot.app)
        for label in ("ANNOUNCE", "SWARM", "AGENT", "BOARD", "LAUNCHPAD", "POOL4",
                      "PROTOCOL", "PORTFOLIO", "EARNINGS", "SWARM TOKENS", "BAY 11", "BAY 12"):
            assert label in text


async def test_planned_cards_focus_but_empty_bays_do_not_and_arrows_follow_geometry():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data()
        rack.focus_card("announce")
        rack.move_focus("down")
        assert rack.focused_card == "protocol"
        rack.move_focus("right")
        assert rack.focused_card == "swarm-tokens"
        rack.move_focus("down")
        assert rack.focused_card == "earnings"
        rack.move_focus("left")
        assert rack.focused_card == "portfolio"
        rack.move_focus("down")
        assert rack.focused_card == "portfolio"
        assert all(not card.can_focus for card in rack.query(".empty"))


async def test_each_planned_card_activates_an_explanation_without_destination():
    class Messages(RackApp):
        opened = []

        def on_surfboard_rack_card_activated(self, event):
            self.opened.append(event)

    async with Messages().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        for key in ("swarm-tokens", "portfolio", "earnings"):
            rack.focus_card(key)
            rack.activate_focused()
        await pilot.pause()
        assert [event.key for event in pilot.app.opened] == ["swarm-tokens", "portfolio", "earnings"]
        assert all(event.destination is None and "planned" in event.detail for event in pilot.app.opened)


@pytest.mark.parametrize("numerator,denominator,expected", [
    (0, 8, "PASS ▱▱▱▱▱▱▱▱"), (4, 8, "PASS ▰▰▰▰▱▱▱▱"),
    (8, 8, "PASS ▰▰▰▰▰▰▰▰"), (0, 0, "PASS —"),
    (None, 8, "PASS —"), (True, 8, "PASS —"), (9, 8, "PASS —"),
    (-1, 8, "PASS —"), (float("inf"), 8, "PASS —"),
])
async def test_ratio_meter_never_fakes_zero_or_clamps_invalid_data(numerator, denominator, expected):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="agent", status="active", primary="seat #420",
            secondary="no attempts" if denominator == 0 else "canonical", destination="agent",
            meter_kind="ratio", numerator=numerator, denominator=denominator, detail="records · read 12:34")])
        await pilot.pause()
        assert expected in painted(pilot.app)


async def test_chart_requires_all_eight_buckets_and_planned_cards_stay_unlit():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="swarm", status="active", primary="1 online", secondary="0 working",
            meter_kind="sparkline", points=[0, 1, 2, 3, 4, 5, 6, 7]),
            dict(key="earnings", status="active", numerator=1, denominator=1, destination="fake")])
        await pilot.pause()
        assert "24H ▁▂▃▄▅▆▇█" in painted(pilot.app)
        planned = rack.query_one("#surfboard-card-earnings", SurfboardCard)
        assert planned.data["destination"] is None
        rack.update_data(surfboard_cards=[dict(key="swarm", meter_kind="sparkline", points=[0, 1])])
        await pilot.pause()
        assert "24H —" in painted(pilot.app)
