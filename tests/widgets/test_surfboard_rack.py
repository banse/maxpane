"""The approved rack is a fixed six-column machine faceplate, not a reflow."""
from textual.app import App
from rich.color import Color
import pytest

from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard


class RackApp(App):
    def compose(self):
        yield SurfboardRack(id="rack")


def activity_strip(app, card):
    rows = [strip.crop(card.region.x, card.region.right) for strip in
            app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
    if card.key == "agent":
        bottom = next(i for i, row in enumerate(rows) if "└" in row.text)
        return rows[bottom + 1]
    return rows[-1]


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
        empty=pilot.app.query_one('#surfboard-card-bay-11',SurfboardCard)
        text='0123456789'*10
        for status in ('active','idle','stale','working','failed','active'):
            card.set_data(dict(primary=text,secondary='7 new replies',status=status))
            await pilot.pause()
            strips=[s.crop(card.region.x,card.region.right) for s in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top=next(i for i,s in enumerate(strips) if '┌' in s.text)
            left,right=strips[top].text.index('┌'),strips[top].text.index('┐'); inside=right-left-1
            assert '⊙ ONCHAIN NEWS' in '\n'.join(s.text for s in strips)
            header = next(s for s in strips[top] if 'LATEST' in s.text)
            assert strips[top].text.strip('│┌┐─ ') == 'LATEST'
            assert not header.style.bold and header.style.color == inset_border_color(strips[top])
            assert [s.text[left+1:right] for s in strips[top+1:top+4]]==[
                text[:inside],text[inside:inside*2],text[inside*2:inside*3-3]+'...']
            assert strips[top+4].text[left+1:right].strip('─ ') == '7 new'
            ink=next(iter(strips[top+1].crop(left+1,left+2))).style
            empty_ink=next(seg.style.color for strip in pilot.app.screen._compositor.render_strips()[empty.region.y:empty.region.bottom]
                           for seg in strip.crop(empty.region.x,empty.region.right) if 'empty slot' in seg.text)
            assert ink.color==(card.rich_style.color if status=='active' else empty_ink)
            edge=next(iter(strips[top].crop(left,left+1))).style.color.get_truecolor()
            neutral=neutral_inset_color(pilot.app)
            status_ink=(Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                        if status in ('active','working') else pilot.app.ansi_theme.ansi_colors[1 if status=='failed' else 3])
            expected=neutral if status in ('idle','stale') else status_ink
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


@pytest.mark.parametrize('size', [(149,45),(140,36)])
async def test_leader_and_coins_digit_labels_exact_counts_and_launch_color(size):
    async with RackApp().run_test(size=size) as pilot:
        for key,primary,footer,label,outer,glyphs in [
            ('board','527','4,176 accepted jobs','TOP AGENT','LEADERBOARD',['╭─╴╶─╮╶─┐','╰─╮┌─┘  │','╶─╯╰─╴  ╵']),
            ('launchpad','208','0 new','COINS','LAUNCHPAD',['╶─╮╭─╮╭─╮','┌─┘│ │├─┤','╰─╴╰─╯╰─╯']),
        ]:
            card=pilot.app.query_one('#surfboard-card-'+key,SurfboardCard)
            for status in ('active','idle'):
                card.set_data(dict(primary=primary,secondary=footer,status=status))
                await pilot.pause()
                strips=[s.crop(card.region.x,card.region.right) for s in
                    pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
                top=next(i for i,s in enumerate(strips) if '┌' in s.text)
                assert '⊙ '+outer in '\n'.join(s.text for s in strips)
                header = next(s for s in strips[top] if label in s.text)
                assert not header.style.bold and header.style.color == inset_border_color(strips[top])
                assert all(g in s.text for g,s in zip(glyphs,strips[top+1:top+4]))
                expected='4,176 jobs' if key=='board' else footer
                assert strips[top+4].text.strip('│└┘─ ') == expected


def painted(app):
    return "\n".join("".join(segment.text for segment in strip)
                     for strip in app.screen._compositor.render_strips())


@pytest.mark.parametrize("key,status,ink", [
    ("bay-10", "unassigned", None), ("bay-11", "unassigned", None),
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
            card.set_data(dict(status=status, primary="IDMD #420", secondary=slots,
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
            meter = strips[top + 5].text
            if activity == "unavailable":
                assert meter.startswith("│  — — ")
                assert not any(glyph in meter for glyph in "▰▱")
            elif activity == "offline":
                assert meter == '│  OFF ' + '▱' * (card.region.width - 10) + '  │'
            else:
                cells = card.region.width - 11
                bar = "▰" * cells
                assert meter == f"│  {activity.upper()} {bar}  │"


async def test_card_activity_colors_update_from_current_counts():
    async with RackApp().run_test(size=(149,45)) as pilot:
        for key,status,primary,secondary,ink in [
            ('pool4','active','8.77','USD',2),
            ('pool4','idle','8.77','USD',3),
            ('board','stale','527','4,176 accepted jobs',3),
            ('launchpad','idle','208','0 new',3),
            ('agent','idle','IDMD #420','0 of 3 slots',3),
            ('agent','offline','IDMD #420','0 of 3 slots',1),
            ('swarm-tokens','idle','118','0 new',3),
            ('protocol','active','33,279','IMD',2),
            ('protocol','ready','33,279','IMD',11),
            ('protocol','experimental','33,279','IMD',3),
            ('protocol','stale','33,279','IMD',3),
            ('protocol','unavailable','33,279','IMD',3),
            ('protocol','experimental','unavailable','IMD',3),
            ('protocol','experimental','33,279','IMD',3),
        ]:
            card=pilot.app.query_one(f'#surfboard-card-{key}',SurfboardCard)
            card.set_data(dict(status=status,primary=primary,secondary=secondary))
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
            assert 'BURN' in strips[-1].text
            assert '‹ widen' not in str(card.border_title)


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
        for label in ("ONCHAIN NEWS", "SWARM", "AGENT", "LEADERBOARD", "LAUNCHPAD", "POOL4",
                      "PROTOCOL", "PORTFOLIO", "BAY 10", "LAUNCHES", "BAY 11", "BAY 12"):
            assert label in text


async def test_empty_bays_do_not_focus_and_arrows_follow_new_geometry():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data()
        rack.focus_card("announce")
        rack.move_focus("down")
        assert rack.focused_card == "launchpad"
        rack.move_focus("right")
        assert rack.focused_card == "portfolio"
        rack.move_focus("up")
        assert rack.focused_card == "board"
        rack.move_focus("left")
        assert rack.focused_card == "protocol"
        rack.move_focus("left")
        assert rack.focused_card == "pool4"
        rack.move_focus("left")
        assert rack.focused_card == "swarm-tokens"
        rack.focus_card("portfolio")
        rack.move_focus("down")
        assert rack.focused_card == "agent"
        rack.move_focus("right")
        assert rack.focused_card == "agent"
        rack.move_focus("down")
        assert rack.focused_card == "agent"
        assert all(not card.can_focus for card in rack.query(".empty"))


async def test_live_cards_route_and_empty_bays_do_not_activate():
    class Messages(RackApp):
        opened = []

        def on_surfboard_rack_card_activated(self, event):
            self.opened.append(event)

    async with Messages().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        for key in ("swarm-tokens", "portfolio"):
            rack.focus_card(key)
            rack.activate_focused()
        await pilot.pause()
        rack.query_one("#surfboard-card-bay-10", SurfboardCard).action_activate()
        await pilot.pause()
        assert [event.key for event in pilot.app.opened] == ["swarm-tokens", "portfolio"]
        live, portfolio = pilot.app.opened
        assert live.destination == "swarm-tokens" and "production-chain markets" in live.detail
        assert portfolio.destination == "portfolio" and "holdings and ready claims" in portfolio.detail


@pytest.mark.parametrize("numerator,denominator,expected", [
    (0, 8, "IDLE ▱▱▱▱▱▱▱▱▱▱▱▱▱"), (4, 8, "IDLE ▰▰▰▰▰▰▱▱▱▱▱▱▱"),
    (8, 8, "IDLE ▰▰▰▰▰▰▰▰▰▰▰▰▰"), (0, 0, "IDLE —"),
    (None, 8, "IDLE —"), (True, 8, "IDLE —"), (9, 8, "IDLE —"),
    (-1, 8, "IDLE —"), (float("inf"), 8, "IDLE —"),
])
async def test_ratio_meter_never_fakes_zero_or_clamps_invalid_data(numerator, denominator, expected):
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="agent", status="active", primary="seat #420",
            secondary="no attempts" if denominator == 0 else "canonical", destination="agent",
            meter_kind="ratio", meter_state="idle", numerator=numerator, denominator=denominator,
            detail="observed stop · read 12:34")])
        await pilot.pause()
        assert expected in painted(pilot.app)


async def test_chart_requires_all_eight_buckets_and_empty_bays_stay_unlit():
    async with RackApp().run_test(size=(149, 45)) as pilot:
        rack = pilot.app.query_one(SurfboardRack)
        rack.update_data(surfboard_cards=[dict(key="swarm", status="active", primary="1 online", secondary="0 working",
            meter_kind="sparkline", points=[0, 1, 2, 3, 4, 5, 6, 7]),
            dict(key="bay-10", status="active", numerator=1, denominator=1, destination="fake")])
        await pilot.pause()
        assert "24H ▁▁▂▂▃▃▄▅▅▆▆▇▇█" in painted(pilot.app)
        empty = rack.query_one("#surfboard-card-bay-10", SurfboardCard)
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
            assert str(card.border_title) == "⊙ SWARM"
        card.set_data(dict(card.data, points=None))
        await pilot.pause()
        footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(card.region.x, card.region.right)
        assert footer.text.startswith("╰─ 24H — ")
        assert not any(char in footer.text for char in "▁▂▃▄▅▆▇█")


async def test_all_other_card_footers_align_left_and_fill_width_on_resize():
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload

    labels = {"protocol": "BURN", "board": "IDLE",
              "portfolio": "ASSETS", "bay-10": "AUX",
              "bay-11": "AUX", "bay-12": "AUX"}
    placeholders = {"portfolio", "bay-10", "bay-11", "bay-12"}
    payload = hub_payload()
    for data in payload["surfboard_cards"]:
        if data["key"] in labels:
            data.update(numerator=1, denominator=2, meter_kind="ratio")
            if data["key"] in ("agent", "board"):
                data["meter_state"] = "idle"
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for width in (149, 180, 144, 149):
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            strips = app.hub._compositor.render_strips()
            for key, label in labels.items():
                card = app.hub.query_one(f"#surfboard-card-{key}", SurfboardCard)
                footer = strips[card.region.bottom - 1].crop(card.region.x, card.region.right)
                prefix, suffix = ("┗╍ ", " ╍┛") if key.startswith("bay-") else ("╰─ ", " ─╯")
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


@pytest.mark.parametrize('size', [(149, 45), (140, 36)])
async def test_tokens_card_latest_rows_and_news_border_refresh(size):
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload
    payload = hub_payload()
    data = next(c for c in payload['surfboard_cards'] if c['key'] == 'swarm-tokens')
    data['latest_launches'][0]['symbol'] = 'VERDIGREEN'
    async with HubHarness(payload).run_test(size=size) as pilot:
        await pilot.pause()
        card = pilot.app.hub.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for status, footer in [('active', '2 new'), ('idle', '0 new')]:
            card.set_data(dict(data, status=status, secondary=footer))
            await pilot.pause()
            strips = [strip.crop(card.region.x, card.region.right) for strip in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(i for i, strip in enumerate(strips) if '┌' in strip.text)
            assert '⊙ LAUNCHES' in '\n'.join(s.text for s in strips)
            assert '‹' not in strips[0].text
            assert 'SWARM TOKENS' not in '\n'.join(s.text for s in strips)
            header = next(s for s in strips[top] if 'LATEST' in s.text)
            expected = (Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor()
                        if status == 'active' else neutral_inset_color(pilot.app))
            assert not header.style.bold and header.style.color == inset_border_color(strips[top])
            for strip, words, icon in zip(strips[top+1:top+4],
                    [('2h', 'VERDIGREEN'), ('4h', 'RAI'), ('5h', 'TDEMO')], ['✔', '⚠', '—']):
                assert strip.text.strip('│ ').split() == [icon, *words]
                for segment in strip:
                    if any(word in segment.text for word in words):
                        assert segment.style.color == card.rich_style.color
                        assert not segment.style.dim
                marker = next(s for s in strip if icon in s.text)
                expected_ink = (Color.parse(pilot.app.get_css_variables()['accent']).get_truecolor() if icon == '✔'
                                else pilot.app.ansi_theme.ansi_colors[3] if icon == '⚠' else card.rich_style.color.get_truecolor())
                assert marker.style.color.get_truecolor() == expected_ink
            assert strips[top+4].text.strip('│└┘─ ') == (footer if status == 'active' else '')
            bottom = next(s for s in strips[top+4] if '└' in s.text)
            assert not bottom.style.bold and bottom.style.color.get_truecolor() == expected


async def test_latest_launch_marker_requires_fresh_matching_quote_and_two_sides():
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload
    async with HubHarness(hub_payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = pilot.app.hub.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for lp, freshness, quote, icon in [
            ('two-sided', 'ok', 'ETH', '✔'), ('two-sided', 'ok', 'IMD', '✔'),
            ('two-sided', 'ok', 'USDC', '—'), ('two-sided', 'stale', 'ETH', '—'),
            ('withdrawn', 'ok', 'ETH', '—'), ('unknown', 'ok', 'ETH', '—'),
            ('one-token', 'ok', 'IMD', '⚠'), ('one-quote', 'ok', 'ETH', '⚠'),
        ]:
            card.set_data(dict(status='idle', secondary='0 new', latest_launches=[dict(
                age_s=7200, symbol='SFPT', chain='eth', lp_state=lp, liquidity_state=freshness, paired_symbol=quote)]))
            await pilot.pause()
            strips = [s.crop(card.region.x, card.region.right) for s in
                      pilot.app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            row = next(s.text for s in strips if 'SFPT' in s.text)
            assert row.strip('│ ').split() == [icon, '2h', 'SFPT']


async def test_latest_launch_empty_short_and_hostile_rows_stay_fitted_on_resize():
    from tests.screens.test_surfboard_layout import HubHarness
    from tests.surfboard_fixtures import hub_payload
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-swarm-tokens', SurfboardCard)
        for width in (149, 180, 140, 149):
            await pilot.resize_terminal(width, 45)
            for latest, expected in [(None, 'unavailable'), ([], 'no launches'), ([dict(
                age_s=None, symbol='[/x]\n' + '界' * 20 + '\x1b\u202e', chain='base',
                lp_state='unknown', liquidity_state='unknown')], '[/')]:
                card.set_data(dict(status='idle', secondary='0 new', latest_launches=latest))
                await pilot.pause()
                strips = [s.crop(card.region.x, card.region.right) for s in
                          app.hub._compositor.render_strips()[card.region.y:card.region.bottom]]
                top = next(i for i, s in enumerate(strips) if '┌' in s.text)
                left, right = strips[top].text.index('┌'), strips[top].text.index('┐')
                body = [s.crop(left+1, right).text.strip() for s in strips[top+1:top+4]]
                assert sum(bool(row) for row in body) == 1
                assert any(expected in row for row in body)
                assert '\x1b' not in '\n'.join(body) and '\u202e' not in '\n'.join(body)
                assert all(s.crop(right, right+1).text == '│' for s in strips[top+1:top+4])
                assert '‹' not in strips[0].text
                assert 'BASE' not in '\n'.join(body)
                if latest:
                    assert body[0].startswith('— —') and '…' in body[0]
                    assert '[/' in body[0]  # literal markup survived safely
