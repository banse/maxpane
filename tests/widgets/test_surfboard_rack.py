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
