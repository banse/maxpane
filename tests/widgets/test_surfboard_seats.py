"""Four independent inline agent seats, observed through the compositor."""
import pytest
from rich.color import Color
from textual.widgets import Input

from maxpane_dashboard.screens.seat_input import SeatInputScreen
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard, SurfboardRack
from tests.widgets.test_surfboard_rack import RackApp


KEYS = ("agent", "agent-2", "agent-3", "agent-4")


def rows(app, card):
    return [strip.crop(card.region.x, card.region.right) for strip in
            app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]


class SeatApp(RackApp):
    def __init__(self):
        super().__init__()
        self.submitted, self.opened = [], []

    def on_surfboard_rack_seat_submitted(self, event):
        self.submitted.append((event.seat_slot, event.value))

    def on_surfboard_rack_card_activated(self, event):
        self.opened.append(event)


@pytest.mark.parametrize("size", [(149, 45), (144, 35)])
async def test_four_empty_agent_seats_have_unframed_native_colored_inputs(size):
    async with SeatApp().run_test(size=size) as pilot:
        pilot.app.register_theme(THEMES["matrix"])
        pilot.app.theme = "matrix"
        rack = pilot.app.query_one(SurfboardRack)
        selector = SeatInputScreen(current=3, saver=lambda value: None)
        await pilot.app.push_screen(selector)
        await pilot.pause()
        native = selector.query_one(Input)
        native.focus()
        await pilot.pause()
        native_background, native_color = native.styles.background, native.styles.color
        native_tint = native.styles.background_tint
        native_fill = next(iter(pilot.app.screen._compositor.render_strips()[native.content_region.y]
                                .crop(native.content_region.right - 1, native.content_region.right))).style.bgcolor
        pilot.app.pop_screen()
        await pilot.pause()
        for slot, key in enumerate(KEYS):
            card = rack.query_one(f"#surfboard-card-{key}", SurfboardCard)
            field = card.query_one(Input)
            painted = rows(pilot.app, card)
            top = next(i for i, row in enumerate(painted) if "EMPTY SEAT" in row.text)
            assert "⊙ AGENT" in painted[0].text
            assert "EMPTY SEAT" in painted[top].text
            assert not any(char in row.text for row in painted for char in "┌┐└┘")
            assert "type in seat no" in painted[top + 4].text
            assert painted[-1].text == "╰─ EMPTY " + "▱" * (card.region.width - 12) + " ─╯"
            assert card.can_focus and card.data["seat_slot"] == slot
            assert card.data["token_id"] is None and card.data["destination"] is None
            assert field.display and field.region.height == 3
            assert field.region.y == card.region.y + top + 1
            assert field.region.x > card.content_region.x
            assert field.region.right < card.content_region.right
            background = Color.parse(pilot.app.get_css_variables()["surface"])
            assert card.styles.background == field.styles.background == native_background
            assert field.styles.color == native_color
            assert all(segment.style.bgcolor == background for segment in painted[top].crop(1, card.region.width - 1))
            accent = Color.parse(pilot.app.get_css_variables()["accent"])
            for focused in (False, True):
                if focused:
                    field.focus()
                    await pilot.pause()
                    assert field.styles.background_tint == native_tint
                strips = pilot.app.screen._compositor.render_strips()
                if focused:
                    fill = next(iter(strips[field.content_region.y]
                                     .crop(field.content_region.right - 1, field.content_region.right)))
                    assert fill.style.bgcolor == native_fill
                for y in (field.region.y, field.region.bottom - 1):
                    edge = strips[y].crop(field.region.x, field.region.right)
                    assert any(segment.text.strip() for segment in edge)
                    assert all(segment.style.color == accent for segment in edge if segment.text.strip())


async def test_inline_drafts_survive_polling_and_submit_only_their_own_slot():
    async with SeatApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        for slot, key in enumerate(KEYS):
            card = rack.query_one(f"#surfboard-card-{key}", SurfboardCard)
            rack.focus_card(key)
            await pilot.press("enter")
            assert pilot.app.focused is card.query_one(Input)
            await pilot.press("#", str(slot), "7")
            rack.update_data()
            await pilot.pause()
            assert card.query_one(Input).value == f"#{slot}7"
            await pilot.press("enter")
            assert pilot.app.submitted == [(index, f"#{index}7") for index in range(slot + 1)]
            assert not pilot.app.opened
        assert [rack.query_one(f"#surfboard-card-{key}").query_one(Input).value for key in KEYS] == ["#07", "#17", "#27", "#37"]


async def test_click_and_numeric_typing_stay_in_the_empty_seat_input():
    async with SeatApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one("#surfboard-card-agent-3", SurfboardCard)
        field = card.query_one(Input)
        await pilot.pause()
        await pilot.click(field)
        await pilot.press("4", "2", "q", "١", "0")
        assert pilot.app.focused is field and field.value == "420"
        assert pilot.app.query_one(SurfboardRack).focused_card == "agent-3"
        assert not pilot.app.opened and not pilot.app.submitted
        await pilot.press("enter")
        assert pilot.app.submitted == [(2, "420")]
        assert not pilot.app.opened


@pytest.mark.parametrize("token_id", [0, 420])
async def test_saving_seat_hides_input_and_activation_carries_exact_identity(token_id):
    async with SeatApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        await pilot.pause()
        for slot, key in enumerate(KEYS):
            card = rack.query_one(f"#surfboard-card-{key}", SurfboardCard)
            card.action_activate()
            await pilot.pause()
            card.query_one(Input).value = str(token_id)
            card.set_data(dict(token_id=token_id, seat_slot=slot, primary=f"IDMD #{token_id}",
                               secondary="0 of 3 slots", status="idle", meter_state="idle",
                               meter_kind="activity", numerator=43200, denominator=86400,
                               destination="agent"))
            await pilot.pause()
            assert not card.query_one(Input).display
            assert pilot.app.focused is card
            painted = "\n".join(row.text for row in rows(pilot.app, card))
            assert " SEAT " in painted and "0 of 3" in painted and "IDLE" in painted
            assert "EMPTY" not in painted and "type in" not in painted
            await pilot.press("enter")
        assert [(event.key, event.seat_slot, event.token_id, event.destination)
                for event in pilot.app.opened] == [(key, slot, token_id, "agent") for slot, key in enumerate(KEYS)]
        assert not pilot.app.submitted


async def test_news_renders_neutral_text_with_every_agent_seat_assigned():
    async with SeatApp().run_test(size=(149, 45)) as pilot:
        for slot, key in enumerate(KEYS):
            pilot.app.query_one(f"#surfboard-card-{key}").set_data(dict(
                seat_slot=slot, token_id=slot, primary=str(slot), status="idle", secondary="0 of 3 slots"))
        news = pilot.app.query_one("#surfboard-card-announce", SurfboardCard)
        news.set_data(dict(primary="Latest saved announcement", status="idle", secondary="0 new"))
        await pilot.pause()
        assert "Latest saved" in "\n".join(row.text for row in rows(pilot.app, news))
        assert not pilot.app.query(".empty")
