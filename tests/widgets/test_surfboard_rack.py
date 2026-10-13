"""The approved rack is a fixed six-column machine faceplate, not a reflow."""
from textual.app import App
from rich.color import Color
import pytest

from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard


class RackApp(App):
    def compose(self):
        yield SurfboardRack(id="rack")


def inset_border_color(strip):
    return next(segment.style.color for segment in strip if '┌' in segment.text)


def neutral_inset_color(app):
    # Observed neutral inset ink in the two harness palettes. Empty bays and
    # outer captions use a darker ink and cannot stand in for the removed EARNINGS face.
    return Color.parse('#9e9e9e' if app.theme == 'matrix' else '#999999').get_truecolor()


@pytest.mark.parametrize('size', [(149,45),(140,36)])
async def test_latest_post_three_lines_ellipsis_and_age_ink(size):
    async with RackApp().run_test(size=size) as pilot:
        card=pilot.app.query_one('#surfboard-card-announce',SurfboardCard)
        text='0123456789'*10
        for status in ('active','idle','stale','working','failed','active'):
            card.set_data(dict(primary=text,secondary='7 new replies',status=status))
            await pilot.pause()
            strips=[s.crop(card.region.x,card.region.right) for s in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top=next(i for i,s in enumerate(strips) if '┌' in s.text)
            left,right=strips[top].text.index('┌'),strips[top].text.index('┐'); inside=right-left-1
            assert '⊙ ONCHAIN FEED' in '\n'.join(s.text for s in strips)
            header = next(s for s in strips[top] if 'LATEST' in s.text)
            assert strips[top].text.strip('│┌┐─ ') == 'LATEST'
            assert not header.style.bold and header.style.color == inset_border_color(strips[top])
            assert [s.text[left+1:right] for s in strips[top+1:top+4]]==[
                text[:inside],text[inside:inside*2],text[inside*2:inside*3-3]+'...']
            assert strips[top+4].text[left+1:right].strip('─ ') == '7 new'
            ink=next(iter(strips[top+1].crop(left+1,left+2))).style
            # Neutral news ink is independent of the editable AGENT card's surface.
            assert ink.color==(card.rich_style.color if status=='active' else Color.parse('#6f6f6f'))
            edge=next(iter(strips[top].crop(left,left+1))).style.color.get_truecolor()
            neutral=neutral_inset_color(pilot.app)
            status_ink=(Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                        if status in ('active','working') else pilot.app.ansi_theme.ansi_colors[1 if status=='failed' else 3])
            expected=(card.rich_style.color.get_truecolor() if status=='active' else
                      neutral if status in ('idle','stale') else status_ink)
            assert edge==expected
            for row in strips[top:top+5]:
                for x in (left,right):
                    assert next(iter(row.crop(x,x+1))).style.color.get_truecolor()==expected
            footer=next(seg for seg in strips[top+4] if '7 new' in seg.text)
            assert footer.style.color.get_truecolor()==expected


@pytest.mark.parametrize('size', [(149,45),(140,36)])
async def test_post_preview_keeps_unicode_literal_and_address_copy_units(size):
    address='0x1234567890abcdef1234567890abcdef12345678'
    async with RackApp().run_test(size=size) as pilot:
        card=pilot.app.query_one('#surfboard-card-announce',SurfboardCard)
        for text in ('Pay '+address+' then read this long announcement carefully.',
                     '測試界面 '*12, 'a'+'界'*100, '[bold] literal '+'x'*60, 'Short post'):
            card.set_data(dict(primary=text,secondary='0 new replies',status='active'))
            await pilot.pause()
            strips=[s.crop(card.region.x,card.region.right) for s in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top=next(i for i,s in enumerate(strips) if '┌' in s.text)
            left,right=strips[top].text.index('┌'),strips[top].text.index('┐')
            content=strips[top+1:top+4]
            assert all(s.crop(left,left+1).text=='│' and s.crop(right,right+1).text=='│' for s in content)
            if text.startswith('Pay'):
                line=next(s for s in content if '0x' in s.text)
                assert '⧉' in line.text
                copied=[s for s in line if '⧉' in s.text]
                assert address in str(copied[0].style.meta)
                assert not copied[0].style.link  # prose gives no chain identity
            elif text.startswith('[bold]'):
                assert '[bold]' in content[0].text
                assert not next(s.style for s in content[0] if '[bold]' in s.text).bold
            elif text.startswith('a界'):
                assert [s.crop(left+1,right).text.rstrip() for s in content]==[
                    'a'+'界'*(8 if size[0]==149 else 7),
                    '界'*(9 if size[0]==149 else 8), '界'*(7 if size[0]==149 else 6)+'...']
            elif text=='Short post':
                assert 'Short post' in content[0].text
                assert all(not s.crop(left+1,right).text.strip() for s in content[1:])
            if text!='Short post':
                assert content[2].crop(left+1,right).text.rstrip().endswith('...')


@pytest.mark.parametrize('size', [(149, 45), (144, 37)])
async def test_oracles_card_counts_digits_tone_and_unknown_reset(size):
    async with RackApp().run_test(size=size) as pilot:
        app = pilot.app
        card = app.query_one('#surfboard-card-oracles', SurfboardCard)
        for status, primary, subtitle, attested, glyphs in [
            ('assessing', '7', '100 loaded', 86, ['╶─┐', '  │', '  ╵']),
            ('idle', '0', '0 loaded', 0, ['╭─╮', '│ │', '╰─╯']),
            ('stale', '7', 'stale 05:20', 86, ['╶─┐', '  │', '  ╵']),
            ('unavailable', '—', 'unavailable', None, ['', '—', '']),
        ]:
            card.set_data(dict(primary=primary, secondary=subtitle, status=status,
                               numerator=attested, denominator=100, meter_kind='oracles'))
            await pilot.pause()
            strips = card_strips(app, card)
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            assert '⊙ ORACLES' in strips[0].text
            assert 'ASSESSING' in strips[top].text
            for strip, expected in zip(strips[top+1:top+4], glyphs):
                assert strip.text[left+1:right].strip() == expected.strip()
            assert subtitle in strips[top+4].text
            expected_footer = f'{attested} attested' if attested is not None else '— attested'
            assert expected_footer in strips[-1].text
            assert not any(glyph in strips[-1].text for glyph in '▰▱▁▂▃▄▅▆▇█')
            tone = app.ansi_theme.ansi_colors[3] if status == 'assessing' else neutral_inset_color(app)
            for strip in strips[top:top+5]:
                for x in (left, right):
                    assert next(iter(strip.crop(x, x+1))).style.color.get_truecolor() == tone
            for label in ('ASSESSING', subtitle):
                segment = next(s for row in strips for s in row if label in s.text)
                assert segment.style.color.get_truecolor() == tone
            assert card.data['destination'] == 'oracles'
        assert not app.query('#surfboard-card-launchpad')


def painted(app):
    return "\n".join("".join(segment.text for segment in strip)
                     for strip in app.screen._compositor.render_strips())


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
        chart = "▁▁▂▂▃▃▄▅▅▆▆▇▇█" if size[0] == 149 else "▁▁▂▂▃▄▄▅▅▆▇▇█"
        assert strips[-1].text == f"╰─ 24H {chart} ─╯"
        header = next(segment for segment in strips[top] if "AGENTS" in segment.text)
        assert not header.style.bold
        assert header.style.color == inset_border_color(strips[top])


async def test_swarm_working_count_overrides_status_color_and_resets_on_refresh():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one("#surfboard-card-swarm", SurfboardCard)
        for status, secondary, ink in [
            ("stale", "1 working", 2), ("stale", "0 working", 3),
            ("unavailable", "1,000 working", 2), ("stale", "unavailable", 3),
            ("stale", "-1 working", 3), ("stale", "1 online", 3),
            ("stale", "0.5 working", 3), ("active", "0 working", 3),
            ("offline", "1 working", 1),
        ]:
            card.set_data(dict(status=status, primary="894 online", secondary=secondary))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if "┌" in strip.text)
            left, right = strips[top].text.index("┌"), strips[top].text.index("┐")
            expected = (Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()
                        if ink == 2 else neutral_inset_color(pilot.app) if ink == 3
                        else pilot.app.ansi_theme.ansi_colors[ink])
            for row in range(top, top + 5):
                for x in (left, right):
                    edge = next(iter(strips[row].crop(x, x + 1)))
                    assert edge.style.color.get_truecolor() == expected, (status, secondary)


@pytest.mark.parametrize("size", [(149, 45), (144, 36)])
async def test_agent_seat_digits_and_slot_border_follow_working_state(size):
    async with RackApp().run_test(size=size) as pilot:
        card = pilot.app.query_one("#surfboard-card-agent", SurfboardCard)
        for status, slots, activity, remaining in [
            ("working", "2 of 3 slots", "busy", 86400),
            ("idle", "0 of 3 slots", "idle", 43200),
            ("paused", "0 of 3 slots", "idle", 21600),
            ("offline", "0 of 0 slots", "offline", 0),
            ("unavailable", "— of — slots", "unavailable", None),
            ("active", "0 of 3 slots", "idle", 43200),
            ("working", "1 of 3 slots", "busy", 86400),
        ]:
            card.set_data(dict(token_id=420, seat_slot=0, status=status, primary="IDMD #420", secondary=slots,
                               meter_kind="activity", meter_state=activity, numerator=remaining, denominator=86400))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if "┌" in strip.text)
            left, right = strips[top].text.index("┌"), strips[top].text.index("┐")
            assert " SEAT " in strips[top].text and "NUMBER" not in strips[top].text
            header = next(segment for segment in strips[top] if "SEAT" in segment.text)
            assert not header.style.bold
            ink = (Color.parse(pilot.app.get_css_variables()["accent"]).get_truecolor()
                   if status == "working"
                   else pilot.app.ansi_theme.ansi_colors[1] if status == "offline"
                   else neutral_inset_color(pilot.app))
            assert header.style.color == inset_border_color(strips[top])
            for strip, row in zip(strips[top + 1:top + 4], ["╷ ╷╶─╮╭─╮", "╰─┤┌─┘│ │", "  ╵╰─╴╰─╯"]):
                padding = (right - left - 1 - len(row)) // 2
                assert strip.text[left + 1:right] == (" " * padding + row).ljust(right - left - 1)
            assert "slots" not in strips[top + 4].text
            footer_text = "offline" if status == "offline" else slots.removesuffix(" slots")
            footer = next(segment for segment in strips[top + 4] if footer_text in segment.text)
            if status == "offline":
                assert " of " not in strips[top + 4].text
            assert not footer.style.bold and footer.style.color.get_truecolor() == ink
            if activity == "unavailable":
                assert strips[-1].text.startswith("╰─ — — ")
                assert not any(glyph in strips[-1].text for glyph in "▰▱")
            elif activity == "offline":
                assert strips[-1].text == '╰─ OFF ' + '▱' * (card.region.width - 10) + ' ─╯'
            else:
                cells = card.region.width - 11
                bar = "▰" * cells
                assert strips[-1].text == f"╰─ {activity.upper()} {bar} ─╯"


async def test_card_activity_colors_update_from_current_counts():
    async with RackApp().run_test(size=(149,45)) as pilot:
        for key,status,primary,secondary,ink in [
            ('pool4','active','8.77','USD',2),
            ('pool4','idle','8.77','USD',3),
            ('board','stale','527','4,176 accepted jobs',3),
            ('oracles','idle','0','100 loaded',3),
            ('agent','idle','IDMD #420','0 of 3 slots',3),
            ('agent','offline','IDMD #420','0 of 3 slots',1),
            ('swarm-tokens','idle','118','0 new',3),
            ('protocol','active','33,279','IMD',3),
            ('protocol','ready','33,279','IMD',3),
            ('protocol','experimental','33,279','IMD',3),
            ('protocol','stale','33,279','IMD',3),
            ('protocol','unavailable','33,279','IMD',3),
            ('protocol','experimental','unavailable','IMD',3),
            ('protocol','experimental','33,279','IMD',3),
        ]:
            card=pilot.app.query_one(f'#surfboard-card-{key}',SurfboardCard)
            card.set_data(dict(token_id=420 if key == "agent" else None, status=status,primary=primary,secondary=secondary))
            await pilot.pause()
            strips=[strip.crop(card.region.x,card.region.right) for strip in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            edge=next(segment for strip in strips for segment in strip if '┌' in segment.text)
            expected=(Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                      if ink==2 else neutral_inset_color(pilot.app) if ink==3
                      else pilot.app.ansi_theme.ansi_colors[ink])
            assert edge.style.color.get_truecolor()==expected


@pytest.mark.parametrize('size',[(149,45),(140,36)])
@pytest.mark.parametrize('key,primary,secondary,label,expected,green,footer_text',[
    ('pool4','8.77','USD','IMD PRICE',
     ['╭─╮ ╶─┐╶─┐','├─┤   │  │','╰─╯•  ╵  ╵'],True,'USD'),
])
async def test_pool4_digit_face(size,key,primary,secondary,label,expected,green,footer_text):
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
             if green else neutral_inset_color(pilot.app))
        assert not header.style.bold and header.style.color == inset_border_color(strips[top])
        for strip,row in zip(strips[top+1:top+4],expected):
            padding=(right-left-1-len(row))//2
            assert strip.text[left+1:right]==(' '*padding+row).ljust(right-left-1)
        footer=next(segment for segment in strips[top+4] if footer_text in segment.text)
        assert strips[top+4].text[left+1:right].strip('─ ')==footer_text
        assert not footer.style.bold and footer.style.color.get_truecolor()==ink


@pytest.mark.parametrize('size', [(180,45), (149,45), (140,36)])
async def test_protocol_stats_align_labels_and_values_with_inner_padding(size):
    from maxpane_dashboard.data.surfboard import cards

    async with RackApp().run_test(size=size) as pilot:
        card = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
        for values, expected in [
            ((33279, 5873, 3786), ['33k', '6k', '4k']),
            ((1234567, 0, 12.8), ['1M', '0', '13']),
            ((999999, 999999, 999999999), ['1M', '1M', '1B']),
            ((None, 5873, float('nan')), ['—', '6k', '—']),
            ((None, None, None), ['—', '—', '—']),
        ]:
            data = dict(zip(('pool4_total_burned', 'pool4_total_rewarded', 'pool4_total_fee_token'), values))
            row = next(row for row in cards(data, {}, now=100) if row['key'] == 'protocol')
            card.set_data(dict(row, secondary='0.47% of supply'))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            assert strips[top].text[left+1:right].strip('─ ') == 'STATS'
            unit_columns, label_columns = set(), set()
            for strip, name, value in zip(strips[top+1:top+4], ('burned', 'rewarded', 'fees'), expected):
                line = strip.text[left+1:right]
                assert line.split() == [name, value, 'IMD']
                assert line.startswith(' ' + name) and line.endswith(' ')
                assert not line[line.index('IMD')+3:].strip()
                unit_columns.add(line.index('IMD'))
                label_columns.add(line.index(name))
                assert '★' not in line and ':' not in line
            assert len(unit_columns) == len(label_columns) == 1
            assert strips[top+4].text[left+1:right].strip('─ ') == ''
            assert '0.47% burned' in strips[-1].text and 'BURN' not in strips[-1].text
            assert '‹' not in str(card.border_title)


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
        assert terminal.region.bottom == rack.content_region.bottom
        assert cards[10].region.bottom == cards[11].region.bottom <= terminal.region.bottom
        assert terminal.region.x > cards[6].region.x
        assert terminal.region.right < cards[7].region.x
        text = painted(pilot.app)
        for label in ("ONCHAIN FEED", "BUILT BY SWARM", "AGENT", "FLEET", "ORACLES", "POOL4",
                      "PROTOCOL", "WIP", "TOKENS", "EMPTY SEAT"):
            assert label in text


async def test_all_agent_seats_focus_and_arrows_follow_new_geometry():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data()
        rack.focus_card("announce")
        rack.move_focus("down")
        assert rack.focused_card == "oracles"
        rack.move_focus("right")
        assert rack.focused_card == "swarm-tokens"
        rack.move_focus("up")
        assert rack.focused_card == "board"
        rack.move_focus("left")
        assert rack.focused_card == "protocol"
        rack.move_focus("left")
        assert rack.focused_card == "pool4"
        rack.move_focus("left")
        assert rack.focused_card == "work"
        rack.focus_card("swarm-tokens")
        rack.move_focus("down")
        assert rack.focused_card == "agent-2"
        rack.move_focus("left")
        assert rack.focused_card == "agent"
        rack.move_focus("down")
        assert rack.focused_card == "agent-3"
        rack.move_focus("right")
        assert rack.focused_card == "agent-4"
        assert all(card.can_focus for card in rack.query(".empty"))


async def test_live_cards_route_and_empty_seats_focus_input_without_opening():
    class Messages(RackApp):
        opened = []

        def on_surfboard_rack_card_activated(self, event):
            self.opened.append(event)

    async with Messages().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        for key in ("swarm-tokens", "work"):
            rack.focus_card(key)
            rack.activate_focused()
        await pilot.pause()
        rack.query_one("#surfboard-card-agent-2", SurfboardCard).action_activate()
        await pilot.pause()
        assert [event.key for event in pilot.app.opened] == ["swarm-tokens", "work"]
        live, work = pilot.app.opened
        assert live.destination == "swarm-tokens" and "production-chain markets" in live.detail
        assert work.destination == "work" and "WORK IN PROGRESS" in work.detail


@pytest.mark.parametrize("numerator,denominator,expected", [
    (0, 8, "IDLE ▱▱▱▱▱▱▱▱▱▱▱▱▱"), (4, 8, "IDLE ▰▰▰▰▰▰▱▱▱▱▱▱▱"),
    (8, 8, "IDLE ▰▰▰▰▰▰▰▰▰▰▰▰▰"), (0, 0, "IDLE —"),
    (None, 8, "IDLE —"), (True, 8, "IDLE —"), (9, 8, "IDLE —"),
    (-1, 8, "IDLE —"), (float("inf"), 8, "IDLE —"),
])
async def test_ratio_meter_never_fakes_zero_or_clamps_invalid_data(numerator, denominator, expected):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="agent", token_id=420, seat_slot=0, status="active", primary="seat #420",
            secondary="no attempts" if denominator == 0 else "canonical", destination="agent",
            meter_kind="ratio", meter_state="idle", numerator=numerator, denominator=denominator,
            detail="observed stop · read 12:34")])
        await pilot.pause()
        assert expected in painted(pilot.app)


async def test_chart_requires_all_eight_buckets_and_empty_seats_stay_unlit():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="swarm", status="active", primary="1 online", secondary="0 working",
            meter_kind="sparkline", points=[0, 1, 2, 3, 4, 5, 6, 7]),
            dict(key="agent-2", token_id=None, status="active", numerator=1, denominator=1, destination="fake")])
        await pilot.pause()
        assert "24H ▁▁▂▂▃▃▄▅▅▆▆▇▇█" in painted(pilot.app)
        empty = rack.query_one("#surfboard-card-agent-2", SurfboardCard)
        assert empty.data["destination"] is None
        rack.update_data(surfboard_cards=[dict(key="swarm", meter_kind="sparkline", points=[0, 1])])
        await pilot.pause()
        assert "24H —" in painted(pilot.app)


async def test_swarm_outer_footer_stretches_history_on_resize_and_keeps_unknown_left():
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload

    payload = hub_payload()
    next(card for card in payload["surfboard_cards"] if card["key"] == "swarm")["points"] = list(range(8))
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one("#surfboard-card-swarm", SurfboardCard)
        for width, chart in [(149, "▁▁▂▂▃▃▄▅▅▆▆▇▇█"), (180, "▁▁▁▂▂▃▃▃▄▄▅▅▆▆▆▇▇██"),
                             (140, "▁▁▂▂▃▄▄▅▅▆▇▇█"), (149, "▁▁▂▂▃▃▄▅▅▆▆▇▇█")]:
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(card.region.x, card.region.right)
            assert footer.text == f"╰─ 24H {chart} ─╯"
            assert str(card.border_title) == "⊙ BUILT BY SWARM"
        card.set_data(dict(card.data, points=None))
        await pilot.pause()
        footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(card.region.x, card.region.right)
        assert footer.text.startswith("╰─ 24H — ")
        assert not any(char in footer.text for char in "▁▂▃▄▅▆▇█")


async def test_all_other_card_footers_align_left_and_fill_width_on_resize():
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload

    labels = {"board": "IDLE", "agent": "IDLE"}
    placeholders = set()
    payload = hub_payload()
    for data in payload["surfboard_cards"]:
        if data["key"] in labels:
            data.update(numerator=1, denominator=2, meter_kind="ratio")
            if data["key"] in ("agent", "board"):
                data["meter_state"] = "idle"
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for width in (149, 180, 148, 149):
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            strips = app.hub._compositor.render_strips()
            for key, label in labels.items():
                card = app.hub.query_one(f"#surfboard-card-{key}", SurfboardCard)
                footer = strips[card.region.bottom - 1].crop(card.region.x, card.region.right)
                prefix, suffix = "╰─ ", " ─╯"
                assert footer.text.startswith(prefix + label + " ")
                assert footer.text.endswith(suffix)
                bar = footer.text[len(prefix + label + " "):-len(suffix)]
                assert bar and set(bar) <= {"▰", "▱"}
                assert bar.count("▰") == (0 if key in placeholders else len(bar) // 2)
                for segment in footer:
                    if "▰" in segment.text:
                        assert segment.style.color.get_truecolor() == app.ansi_theme.ansi_colors[3 if key == "protocol" else 2]
        for key in labels.keys() - placeholders:
            card = app.hub.query_one(f"#surfboard-card-{key}", SurfboardCard)
            card.set_data(dict(card.data, numerator=None))
        await pilot.pause()
        strips = app.hub._compositor.render_strips()
        for key in labels.keys() - placeholders:
            card = app.hub.query_one(f"#surfboard-card-{key}", SurfboardCard)
            footer = strips[card.region.bottom - 1].crop(card.region.x, card.region.right).text
            assert footer.startswith(f"╰─ {labels[key]} — ")
            assert "▰" not in footer and "▱" not in footer


def token_card_data():
    from tests.surfboard_fixtures import hub_payload
    return next(card for card in hub_payload()['surfboard_cards'] if card['key'] == 'swarm-tokens')


def card_strips(app, card):
    return [strip.crop(card.region.x, card.region.right) for strip in
            app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]


@pytest.mark.parametrize('size', [(149, 45), (140, 36)])
async def test_tokens_ranked_rows_direction_ink_volume_footer_and_activity(size):
    data = token_card_data()
    async with RackApp().run_test(size=size) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for status, footer in [('active', '2 new'), ('idle', '0 new')]:
            card.set_data(dict(data, status=status, secondary=footer, meter_kind='sparkline',
                               meter_state='partial', points=list(range(8))))
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            assert '⊙ TOKENS' in strips[0].text
            assert '‹' not in strips[0].text
            header = next(s for s in strips[top] if 'LAST 24h' in s.text)
            expected = (Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                        if status == 'active' else neutral_inset_color(pilot.app))
            assert strips[top].text.strip('│┌┐─ ') == 'LAST 24h'
            assert not header.style.bold and header.style.color == inset_border_color(strips[top])
            for strip, words, icon in zip(strips[top+1:top+4],
                    [('2h', 'SFPT'), ('5h', 'RAI'), ('4h', 'TDEMO')], ['↑', '↓', '']):
                assert strip.text.strip('│ ').split() == [*words, *([icon] if icon else [])]
                left = strips[top].text.index('┌')
                assert strip.crop(left+1, left+3).text == ' ' + words[0][0]
                right = strips[top].text.index('┐')
                assert strip.crop(right-1, right).text == (icon or ' ')
                for segment in strip:
                    if any(word in segment.text for word in words):
                        assert segment.style.color == card.rich_style.color
                        assert not segment.style.dim
                if not icon:
                    continue
                marker = next(s for s in strip if icon in s.text)
                expected_ink = (pilot.app.ansi_theme.ansi_colors[2] if icon == '↑'
                                else pilot.app.ansi_theme.ansi_colors[1] if icon == '↓' else card.rich_style.color.get_truecolor())
                assert marker.style.color.get_truecolor() == expected_ink
            assert strips[top+4].text.strip('│└┘─ ') == (footer if status == 'active' else '')
            bottom = next(s for s in strips[top+4] if '└' in s.text)
            assert not bottom.style.bold and bottom.style.color.get_truecolor() == expected
            assert strips[-1].text.strip('╰╯─ ').startswith('24h ')
            assert 'NEWEST' not in strips[-1].text
            chart = ''.join(s.text for s in strips[-1] if any(c in s.text for c in '▁▂▃▄▅▆▇█'))
            assert chart.strip() and chart.strip().endswith('█')
            assert all(s.style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[2]
                       for s in strips[-1] if any(c in s.text for c in '▁▂▃▄▅▆▇█'))
            assert not any(c in ''.join(s.text for s in strips) for c in '✔⚠')


async def test_token_price_flat_or_missing_is_neutral_despite_legacy_liquidity():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        data = token_card_data()
        for direction, marker in [('up', '↑'), ('down', '↓'), ('flat', ''), (None, '')]:
            data['token_ranking']['rows'] = [dict(data['token_ranking']['rows'][0],
                price_direction=direction, lp_state='two-sided', liquidity_state='ok', paired_symbol='ETH')]
            card.set_data(data)
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            assert strips[top+1].crop(left+1, right).text.split() == ['2h', 'SFPT', *([marker] if marker else [])]
            assert all(not s.crop(left+1, right).text.strip() for s in strips[top+2:top+4])


@pytest.mark.parametrize('state', ['partial', 'stale'])
async def test_token_degraded_ranking_keeps_new_count_and_literal_source_tooltip(state):
    from rich.text import Text
    from maxpane_dashboard.widgets.fmt import hhmm
    data = token_card_data()
    data['token_ranking'].update(state=state, known=2, total=5)
    data['secondary'] = '5 new'
    clock = hhmm(data['token_ranking']['read_ts'])
    data['detail'] = f'TOKENS · 2/5 eligible markets · {state} · source {clock} · [/x] $300\x1b\u202e'
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        card.set_data(data)
        await pilot.pause()
        strips = card_strips(pilot.app, card)
        top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
        assert strips[top+4].text.strip('│└┘─ ') == '5 new'
        assert state not in ''.join(s.text for s in strips)
        assert '2 new' not in ''.join(s.text for s in strips)
        assert inset_border_color(strips[top]).get_truecolor() == neutral_inset_color(pilot.app)
        assert strips[-1].text.strip('╰╯─ ') == '24h —'
        assert isinstance(card.tooltip, Text)
        assert card.tooltip.plain == data['detail'].replace('\x1b', '').replace('\u202e', '')
        assert not card.tooltip.spans


async def test_token_empty_unread_and_unavailable_keep_independent_volume_footer():
    data = token_card_data()
    ranking = data['token_ranking']
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for envelope, body in [
            (None, 'unavailable'),
            (dict(ranking, rows=None, newest=None, state='unavailable', known=0, total=None),
             'unavailable'),
            (dict(ranking, rows=[], newest=None, known=0, total=0), 'no launches'),
            (dict(ranking, rows=[], newest=dict(ranking['newest'], age_s=172800), known=0, total=0),
             'no launches'),
            (dict(ranking, rows=None, state='unavailable', known=0, total=3),
             'unavailable'),
        ]:
            card.set_data(dict(data, token_ranking=envelope, status='idle', secondary='0 new'))
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            assert [s.crop(left+1, right).text.strip() for s in strips[top+1:top+4]] == ['', body, '']
            assert strips[top+4].text.strip('│└┘─ ') == ''
            assert strips[-1].text.strip('╰╯─ ') == '24h —'


async def test_token_hostile_wide_tickers_preserve_age_marker_and_advertise_clipping():
    data = token_card_data()
    hostile = '[/x]\n' + '界' * 20 + '\x1b\u202e'
    data['token_ranking']['rows'] = [dict(data['token_ranking']['rows'][0], age_s=None, symbol=hostile)]
    data['token_ranking']['newest']['symbol'] = hostile
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        card.set_data(data)
        await pilot.pause()
        strips = card_strips(pilot.app, card)
        top = next(i for i, s in enumerate(strips) if '┌' in s.text)
        left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
        row = strips[top+1].crop(left+1, right)
        assert row.text.startswith(' —   [/x]') and '…' in row.text
        assert row.crop(right-left-2, right-left-1).text == '↑'
        assert all(s.crop(right, right+1).text == '│' for s in strips[top+1:top+4])
        assert '‹' in strips[0].text
        assert '\x1b' not in ''.join(s.text for s in strips) and '\u202e' not in ''.join(s.text for s in strips)
        assert strips[-1].text.strip('╰╯─ ') == '24h —'
        assert all(not s.style.bold for s in row if '[/x]' in s.text)


@pytest.mark.parametrize('width', [200, 250])
async def test_token_address_tickers_keep_copy_actions_and_known_chain_links(width):
    address = '0x1234567890abcdef1234567890abcdef12345678'
    data = token_card_data()
    data['token_ranking']['rows'] = [dict(data['token_ranking']['rows'][0], symbol=address)]
    data['token_ranking']['newest']['symbol'] = address
    async with RackApp().run_test(size=(width, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for chain, site in [('eth', 'etherscan.io'), ('base', 'basescan.org'), ('unknown', None)]:
            data['token_ranking']['rows'][0]['chain'] = chain
            data['token_ranking']['newest']['chain'] = chain
            card.set_data(data)
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            rows = [s for s in strips if '0x' in s.text]
            assert len(rows) == 1
            assert 'NEWEST' not in strips[-1].text
            for row in rows:
                icon = next(s for s in row if '⧉' in s.text)
                assert address in str(icon.style.meta) and not icon.style.link
                shown = next(s for s in row if '0x' in s.text)
                assert (site in shown.style.link) if site else not shown.style.link


@pytest.mark.parametrize('module', ['surfboard', 'surf'])
def test_surfboard_and_surf_widgets_import_in_either_order(module):
    import subprocess
    import sys
    other = 'surf' if module == 'surfboard' else 'surfboard'
    result = subprocess.run([sys.executable, '-c',
        f'import maxpane_dashboard.widgets.{module}; import maxpane_dashboard.widgets.{other}'],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('state', ['working', 'idle', 'offline'])
async def test_top_agents_three_aligned_rows_and_medal_stars(state):
    rows = [dict(rank=1, token_id=527, accepted=4184),
            dict(rank=2, token_id=12, accepted=3001),
            dict(rank=3, token_id=3, accepted=987)]
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-board', SurfboardCard)
        card.set_data(dict(primary='527', secondary='4,184 accepted jobs',
                           status=state, top_agents=rows, meter_state='idle',
                           meter_kind='activity', numerator=43200, denominator=86400))
        await pilot.pause()
        strips = card_strips(pilot.app, card)
        top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
        assert 'TOP AGENTS' in strips[top].text
        accepted_ends, seat_starts = [], []
        for strip, seat, accepted, color in zip(strips[top+1:top+4],
                ['527', '12', '3'], ['4,184', '3,001', '987'],
                ['#ffd700', '#c0c0c0', '#cd7f32']):
            assert strip.text.strip('│ ').split() == ['★', seat, accepted]
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            assert strip.crop(left+1, left+3).text == ' ★'
            assert strip.crop(right-len(accepted)-1, right).text == accepted + ' '
            star = next(segment for segment in strip if '★' in segment.text)
            assert star.style.color == Color.parse(color)
            seat_starts.append(strip.text.index(seat))
            accepted_ends.append(strip.text.index(accepted)+len(accepted))
        assert len(set(seat_starts)) == len(set(accepted_ends)) == 1
        assert strips[top+4].text.strip('│└┘─ ') == ''
        assert 'IDLE' in strips[-1].text
        assert '‹' not in strips[0].text


@pytest.mark.parametrize('top_agents,expected', [(None, 'unavailable'), ([], 'no agents')])
async def test_top_agents_unknown_and_empty_are_distinct(top_agents, expected):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-board', SurfboardCard)
        card.set_data(dict(top_agents=top_agents))
        await pilot.pause()
        strips = card_strips(pilot.app, card)
        top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
        assert 'TOP AGENTS' in strips[top].text
        assert expected in strips[top+2].text
        assert all(not strip.text.strip('│ ') for strip in [strips[top+1], strips[top+3]])


async def test_protocol_supply_footer_is_fitted_and_marks_clipping():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-protocol', SurfboardCard)
        card.set_data(dict(primary='★ burned 33k IMD\n★ rewarded 6k IMD\n★ fees 4k IMD',
                           secondary='0.47% of supply', numerator=60, denominator=100))
        for width in [149, 200]:
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            assert 'BURN' not in strips[-1].text and '▰' not in strips[-1].text
            assert '0.47% burned' in strips[-1].text
            assert abs(strips[-1].text.index('0.47% burned') - (card.region.width - len('0.47% burned')) / 2) <= .5
            assert 'of supply' not in strips[-1].text
            assert '‹' not in strips[0].text
        card.set_data(dict(secondary='unavailable'))
        await pilot.pause()
        assert 'unavailable' in card_strips(pilot.app, card)[-1].text
        assert 'unavailable burned' not in card_strips(pilot.app, card)[-1].text


async def test_empty_seat_footer_centers_and_assigned_seat_restores_left_alignment():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-agent-4', SurfboardCard)
        for width in (149, 200):
            await pilot.resize_terminal(width, 45)
            for data in (None, dict(token_id=420, status='idle', primary='IDMD #420',
                                   secondary='0 of 3', meter_state='idle'), None):
                card.set_data(data)
                await pilot.pause()
                row = card_strips(pilot.app, card)[-1].text
                if data is None:
                    assert abs(row.index('Identity.md') - (card.region.width - 11) / 2) <= .5
                else:
                    assert row.startswith('╰─ IDLE ')


async def test_pool4_price_direction_colors_whole_inset_and_resets_to_neutral():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-pool4', SurfboardCard)
        for status in ('active', 'falling', 'idle', 'stale', 'unavailable', 'active'):
            card.set_data(dict(status=status, primary='8.77', secondary='USD'))
            await pilot.pause()
            strips = card_strips(pilot.app, card)
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
            ink = (Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                   if status == 'active' else pilot.app.ansi_theme.ansi_colors[3]
                   if status == 'falling' else neutral_inset_color(pilot.app))
            for row in strips[top:top + 5]:
                for x in (left, right):
                    assert next(iter(row.crop(x, x + 1))).style.color.get_truecolor() == ink
            for row, label in ((strips[top], 'IMD PRICE'), (strips[top + 4], 'USD')):
                assert next(seg.style.color.get_truecolor() for seg in row if label in seg.text) == ink
            digits = next(seg for seg in strips[top + 1] if '╭─╮' in seg.text)
            assert digits.style.color == card.rich_style.color


@pytest.mark.parametrize('accepted,shown', [(None, '—'), (0, '0')])
async def test_top_agent_missing_accepted_count_does_not_become_zero(accepted, shown):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-board', SurfboardCard)
        card.set_data(dict(top_agents=[dict(rank=1, token_id=527, accepted=accepted)]))
        await pilot.pause()
        strips = card_strips(pilot.app, card)
        top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
        assert strips[top+1].text.strip('│ ').split() == ['★', '527', shown]
        assert all(not strip.text.strip('│ ') for strip in strips[top+2:top+4])


@pytest.mark.parametrize('points', [[0]*8, [1, None, 3, 4, 5, 6, 7, 8], None])
async def test_token_volume_footer_shares_swarm_label_color_and_retains_gaps(points):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        card = pilot.app.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        swarm = pilot.app.query_one('#surfboard-card-swarm', SurfboardCard)
        swarm.set_data(dict(meter_kind='sparkline', points=list(range(8))))
        card.set_data(dict(token_card_data(), meter_kind='sparkline', points=points, meter_state='partial'))
        await pilot.pause()
        footer = card_strips(pilot.app, card)[-1]
        label = next(s for s in footer if '24h' in s.text)
        other = next(s for s in card_strips(pilot.app, swarm)[-1] if '24H' in s.text)
        assert label.style.color == other.style.color
        assert '~' not in footer.text and 'NEWEST' not in footer.text
        if points is None:
            assert footer.text.strip('╰╯─ ') == '24h —'
        else:
            assert '—' not in footer.text
            assert ('·' in footer.text) == (None in points)
            assert any(c in footer.text for c in '▁▂▃▄▅▆▇█')


@pytest.mark.parametrize('size', [(149, 45), (144, 37)])
async def test_work_card_approved_digits_workflows_and_step_footer(size):
    async with RackApp().run_test(size=size) as pilot:
        app = pilot.app
        card = app.query_one('#surfboard-card-work', SurfboardCard)
        card.set_data(dict(primary='5', secondary='1 workflow', status='active',
                           work_summary=dict(build=5, review=4)))
        await pilot.pause()
        strips = card_strips(app, card)
        top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
        left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
        assert '⊙ WIP' in strips[0].text
        assert 'WORK IN PROGRESS' not in strips[0].text
        assert 'ACTIVE JOBS' in strips[top].text
        assert [strip.text[left+1:right].strip() for strip in strips[top+1:top+4]] == ['╭─╴', '╰─╮', '╶─╯']
        assert '1 workflow' in strips[top+4].text
        footer = strips[-1].text
        assert ('5 build · 4 review' if card.region.width >= 24 else '5 build · 4 rev') in footer
        assert inset_border_color(strips[top]).get_truecolor() == Color.parse(app.get_css_variables()['accent']).get_truecolor()
        assert card.region.height == app.query_one('#surfboard-card-oracles').region.height
        assert len(app.query(SurfboardCard)) == 12
        assert not app.query('#surfboard-card-portfolio')


async def test_work_card_unknown_idle_and_stale_reset_activity_ink():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        app = pilot.app
        card = app.query_one('#surfboard-card-work', SurfboardCard)
        for state, primary, secondary, counts in [
            ('active', '5', '1 workflow', dict(build=5, review=4)),
            ('idle', '0', '0 workflows', dict(build=0, review=0)),
            ('stale', '5', 'stale 05:20', dict(build=5, review=4)),
            ('unavailable', '—', 'unavailable', dict(build=None, review=None)),
        ]:
            card.set_data(dict(status=state, primary=primary, secondary=secondary, work_summary=counts))
            await pilot.pause()
            strips = card_strips(app, card)
            top = next(s for s in strips if 'ACTIVE JOBS' in s.text)
            expected = Color.parse(app.get_css_variables()['accent']).get_truecolor() if state == 'active' else neutral_inset_color(app)
            assert inset_border_color(top).get_truecolor() == expected
            assert secondary in '\n'.join(s.text for s in strips)
            if state == 'unavailable':
                assert ('— build · — review' if card.region.width >= 24 else '— build · — rev') in strips[-1].text
            if state == 'idle':
                assert ('0 build · 0 review' if card.region.width >= 24 else '0 build · 0 rev') in strips[-1].text
        card.set_data(None)
        await pilot.pause()
        assert ('— build · — review' if card.region.width >= 24 else '— build · — rev') in card_strips(app, card)[-1].text
        assert card.data['destination'] == 'work'
