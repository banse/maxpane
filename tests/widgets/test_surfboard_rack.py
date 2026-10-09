"""The approved rack is a fixed six-column machine faceplate, not a reflow."""
from textual.app import App
from rich.color import Color
import pytest

from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard


class RackApp(App):
    def compose(self):
        yield SurfboardRack(id="rack")


def painted(app):
    return "\n".join("".join(segment.text for segment in strip)
                     for strip in app.screen._compositor.render_strips())


def grey_ink(segment):
    ink=segment.style.color.get_truecolor()
    assert 50 <= ink.red == ink.green == ink.blue < 200
    return ink


@pytest.mark.parametrize("key,status,ink", [
    ("board", "active", 2), ("board", "stale", 3),
    ("board", "unavailable", 3), ("board", "failed", 1),
    ("portfolio", "planned", None), ("bay-11", "unassigned", None),
])
async def test_status_colors_the_taller_inset_without_a_separate_status_row(key, status, ink):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key=key, status=status,
            primary="IDMD #420", secondary="95.9% accepted")])
        rack.focus_card("announce")
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
        if ink == 2:
            outer = rack.query_one("#surfboard-card-announce", SurfboardCard)
            expected = Color.parse(outer.styles.border_top[1].hex).get_truecolor()
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
        assert " AGENTS " in strips[top].text
        assert "ONLINE" not in strips[top].text
        assert strips[top + 4].text[left:right + 1] == "└" + " 27 working ".center(right - left - 1, "─") + "┘"
        for strip, row in zip(strips[top + 1:top + 4], expected):
            padding = (right - left - 1 - len(row)) // 2
            assert strip.text[left + 1:right] == (" " * padding + row).ljust(right - left - 1)
        footer = next(segment for segment in strips[top + 4] if "27 working" in segment.text)
        assert not footer.style.bold
        assert footer.style.color.get_truecolor() == Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()
        assert "24H ▁▂▃▄▅▆▇█" in "\n".join(strip.text for strip in strips)
        header = next(segment for segment in strips[top] if "AGENTS" in segment.text)
        assert header.style.bold
        assert header.style.color.get_truecolor() == Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()


async def test_swarm_working_count_overrides_status_color_and_resets_on_refresh():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one("#surfboard-card-swarm", SurfboardCard)
        for status, secondary, ink in [
            ("stale", "1 working", 2), ("stale", "0 working", 3),
            ("unavailable", "1,000 working", 2), ("stale", "unavailable", 3),
            ("stale", "-1 working", 3), ("stale", "1 online", 3),
            ("stale", "0.5 working", 3), ("active", "0 working", None),
            ("offline", "1 working", 1),
        ]:
            card.set_data(dict(status=status, primary="894 online", secondary=secondary))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if "┌" in strip.text)
            left, right = strips[top].text.index("┌"), strips[top].text.index("┐")
            expected = (Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()
                        if ink == 2 else grey_ink(next(iter(strips[top].crop(left,left+1)))) if ink is None
                        else pilot.app.ansi_theme.ansi_colors[ink])
            for row in range(top, top + 5):
                for x in (left, right):
                    edge = next(iter(strips[row].crop(x, x + 1)))
                    assert edge.style.color.get_truecolor() == expected, (status, secondary)


@pytest.mark.parametrize("size", [(149, 45), (140, 36)])
async def test_agent_seat_digits_and_slot_border_follow_working_state(size):
    async with RackApp().run_test(size=size) as pilot:
        card = pilot.app.query_one("#surfboard-card-agent", SurfboardCard)
        for status, slots in [("working", "2 of 3 slots"), ("idle", "0 of 3 slots"),
                              ("paused", "1 of 3 slots"), ("offline", "0 of 0 slots"),
                              ("unavailable", "— of — slots"), ("active", "0 of 3 slots"),
                              ("working", "1 of 3 slots")]:
            card.set_data(dict(status=status, primary="IDMD #420", secondary=slots,
                               numerator=4, denominator=8))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if "┌" in strip.text)
            left, right = strips[top].text.index("┌"), strips[top].text.index("┐")
            assert " SEAT " in strips[top].text and "NUMBER" not in strips[top].text
            header = next(segment for segment in strips[top] if "SEAT" in segment.text)
            assert header.style.bold
            ink = (Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()
                   if status == "working" else grey_ink(header) if status in ("idle", "active")
                   else pilot.app.ansi_theme.ansi_colors[1 if status == "offline" else 3])
            assert header.style.color.get_truecolor() == ink
            for strip, row in zip(strips[top + 1:top + 4], ["╷ ╷╶─╮╭─╮", "╰─┤┌─┘│ │", "  ╵╰─╴╰─╯"]):
                padding = (right - left - 1 - len(row)) // 2
                assert strip.text[left + 1:right] == (" " * padding + row).ljust(right - left - 1)
            assert "slots" not in strips[top + 4].text
            footer_text = "offline" if status == "offline" else slots.removesuffix(" slots")
            footer = next(segment for segment in strips[top + 4] if footer_text in segment.text)
            if status == "offline":
                assert " of " not in strips[top + 4].text
            assert not footer.style.bold and footer.style.color.get_truecolor() == ink
            assert "PASS ▰▰▰▰▱▱▱▱" in "\n".join(strip.text for strip in strips)


async def test_card_warnings_remain_visible_and_clear_on_recovery():
    async with RackApp().run_test(size=(149,45)) as pilot:
        for key,status,primary,secondary,ink in [
            ('protocol','experimental','5,873','33,279 burned',None),
            ('protocol','stale','5,873','33,279 burned',3),
            ('protocol','unavailable','5,873','33,279 burned',3),
            ('protocol','experimental','unavailable','33,279 burned',3),
            ('protocol','experimental','5,873','33,279 burned',None),
            ('announce','stale','5','1 new post',3),
            ('announce','active','5','0 new posts',None),
        ]:
            card=pilot.app.query_one(f'#surfboard-card-{key}',SurfboardCard)
            card.set_data(dict(status=status,primary=primary,secondary=secondary))
            await pilot.pause()
            strips=[strip.crop(card.region.x,card.region.right) for strip in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            edge=next(segment for strip in strips for segment in strip if '┌' in segment.text)
            if ink is None:
                grey_ink(edge)
            else:
                assert edge.style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[ink]


@pytest.mark.parametrize('size',[(149,45),(140,36)])
@pytest.mark.parametrize('key,primary,secondary,label,expected,green',[
    ('announce','5','0 new posts','SIGNALS',['╭─╴','╰─╮','╶─╯'],False),
    ('announce','5','1 new post','SIGNALS',['╭─╴','╰─╮','╶─╯'],True),
    ('announce','0','12 new posts','SIGNALS',['╭─╮','│ │','╰─╯'],True),
    ('announce','unavailable','unavailable','SIGNALS',['','unavailable',''],False),
    ('protocol','5,873','33,279 burned','IMD REWARDS',
     ['╭─╴ ╭─╮╶─┐╶─╮','╰─╮ ├─┤  │ ─┤','╶─╯,╰─╯  ╵╶─╯'],False),
    ('protocol','99,999','12,345 burned','IMD REWARDS',
     ['╭─╮╭─╮ ╭─╮╭─╮╭─╮','╰─┤╰─┤ ╰─┤╰─┤╰─┤','╶─╯╶─╯,╶─╯╶─╯╶─╯'],False),
    ('protocol','123,456','12,345 burned','IMD REWARDS',['','123,456',''],False),
    ('protocol','1,234,567','12,345 burned','IMD REWARDS',['','1,234,567',''],False),
])
async def test_announce_and_protocol_digit_faces(size,key,primary,secondary,label,expected,green):
    async with RackApp().run_test(size=size) as pilot:
        card=pilot.app.query_one(f'#surfboard-card-{key}',SurfboardCard)
        card.set_data(dict(status='active',primary=primary,secondary=secondary))
        await pilot.pause()
        strips=[strip.crop(card.region.x,card.region.right) for strip in
                pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
        top=next(i for i,strip in enumerate(strips) if '┌' in strip.text)
        left,right=strips[top].text.index('┌'),strips[top].text.index('┐')
        header=next(segment for segment in strips[top] if label in segment.text)
        ink=(Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
             if green else pilot.app.ansi_theme.ansi_colors[3] if primary=='unavailable'
             else grey_ink(header))
        assert header.style.bold and header.style.color.get_truecolor()==ink
        for strip,row in zip(strips[top+1:top+4],expected):
            padding=(right-left-1-len(row))//2
            assert strip.text[left+1:right]==(' '*padding+row).ljust(right-left-1)
        footer=next(segment for segment in strips[top+4] if secondary in segment.text)
        assert not footer.style.bold and footer.style.color.get_truecolor()==ink


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
