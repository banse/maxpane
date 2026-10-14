"""In-situ rack geometry, using the production screen and app stylesheet."""
from pathlib import Path

import pytest
from textual.app import App

from maxpane_dashboard.screens.surfboard import (
    SurfboardScreen, SURFBOARD_FULL_LAYOUT_COLUMNS, SURFBOARD_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surfboard import SurfboardRack, SurfboardTerminal
from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from tests.surfboard_fixtures import HubPayloadManager, STAMP, hub_payload
from tests.screens._sweeps import boundary_set


class HubHarness(App):
    CSS_PATH = Path(__file__).resolve().parents[2] / "maxpane_dashboard/themes/minimal.tcss"

    def __init__(self, payload):
        super().__init__()
        self.hub = SurfboardScreen(HubPayloadManager(payload), name="surfboard")

    def on_mount(self):
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = "matrix"
        self.push_screen(self.hub)


@pytest.mark.parametrize("signals", [0, 1, 4, 9, 11, None])
async def test_news_signal_footer_counts_segments_and_fills_width_on_resize(signals):
    payload = hub_payload()
    news = next(card for card in payload["surfboard_cards"] if card["key"] == "announce")
    news.update(numerator=signals, denominator=11)
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for width, cells in [(149, 9), (180, 14), (140, 9), (149, 9)]:
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            card = app.hub.query_one("#surfboard-card-announce", SurfboardCard)
            footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(
                card.region.x, card.region.right)
            label = footer.text.strip('╰╯─ ')
            assert abs(footer.text.index(label) - (card.region.width - len(label)) / 2) <= .5
            if signals is None:
                assert label == 'SIGNALS —'
                assert "▰" not in footer.text and "▱" not in footer.text
                continue
            if signals > cells + 1:
                assert label == f'SIGNALS {signals}'
                assert "▰" not in footer.text
                continue
            # Drop the gap if that lets the last signal fit beside the label.
            gap = "" if signals > cells else " "
            bar = "▰" * signals + "▱" * (cells + (not gap) - signals)
            assert footer.text == f"╰─ SIGNALS{gap}{bar} ─╯"
            assert "‹ widen" not in str(card.border_title)
            for segment in footer:
                if "▰" in segment.text:
                    assert segment.style.color.get_truecolor() == app.ansi_theme.ansi_colors[2]
                if "SIGNALS" in segment.text:
                    empty = app.hub.query_one("#surfboard-card-pool4", SurfboardCard)
                    caption = next(s for s in app.hub._compositor.render_strips()[empty.region.bottom - 1]
                                   .crop(empty.region.x, empty.region.right) if "sIMD" in s.text)
                    assert segment.style.color == caption.style.color


async def test_news_signal_footer_refresh_and_overflow_remain_exact():
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one("#surfboard-card-announce", SurfboardCard)
        for count, total in [(24, 30), (3, 11), (None, None)]:
            card.set_data(dict(primary="Latest post", secondary="7 new", numerator=count, denominator=total))
            await pilot.pause()
            footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(
                card.region.x, card.region.right).text
            if count == 24:
                assert "SIGNALS 24" in footer and "▰" not in footer
            else:
                assert footer.count("▰") == (count or 0)
                assert "‹ widen" not in str(card.border_title)
                assert ("SIGNALS —" in footer) == (count is None)


async def test_terminal_uses_dashboard_background_and_native_text_colors():
    from rich.color import Color
    from textual.widgets import Input, RichLog

    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for name in ("matrix", "minimal", "fwa"):
            app.theme = name
            await pilot.pause()
            theme = THEMES[name]
            card = app.hub.query_one("#surfboard-card-board", SurfboardCard)
            terminal = app.hub.query_one(SurfboardTerminal)
            terminal.add_reply("palette reply")
            await pilot.pause()
            assert app.hub.styles.background.hex.casefold() == theme.background.casefold()
            assert card.styles.background.hex.casefold() == theme.surface.casefold()
            assert terminal.styles.background == app.hub.styles.background
            assert terminal.command_input.styles.background == app.hub.styles.background
            assert terminal.query_one(".terminal-prompt").styles.background == app.hub.styles.background
            assert terminal.query_one(RichLog).styles.background == app.hub.styles.background
            strips = app.hub._compositor.render_strips()
            value = next(segment for strip in strips for segment in strip
                         if "4,176" in segment.text)
            reply = next(segment for strip in strips for segment in strip
                         if "palette reply" in segment.text)
            assert value.style.bgcolor == Color.parse(theme.background)
            assert value.style.color == card.rich_style.color
            assert reply.style.color == terminal.rich_style.color
            assert reply.style.bgcolor == Color.parse(theme.background)
            rack = app.hub.query_one(SurfboardRack)
            for face in rack.query(SurfboardCard):
                rows = [strip.crop(face.region.x, face.region.right) for strip in
                        strips[face.region.y:face.region.bottom]]
                top = next(i for i, row in enumerate(rows) if "┌" in row.text)
                left, right = rows[top].text.index("┌"), rows[top].text.index("┐")
                assert all(segment.style.bgcolor == Color.parse(theme.surface)
                           for segment in rows[top-1].crop(left, right+1))
                field = face.query_one(Input) if face.empty_seat else None
                for y, row in enumerate(rows[top:top+5], start=face.region.y + top):
                    spans = [(left, right + 1)]
                    if field is not None and y == field.region.y:
                        spans = [(left, field.region.x - face.region.x),
                                 (field.region.right - face.region.x, right + 1)]
                    assert all(segment.style.bgcolor == Color.parse(theme.background)
                               for start, end in spans for segment in row.crop(start, end))
            rack.focus_card("board")
            await pilot.pause()
            assert card.styles.border_top[1].hex.casefold() == theme.accent.casefold()
            prompt = terminal.query_one(".terminal-prompt")
            for focused, ink in ((False, "#345533"), (True, "#9fc99c")):
                if focused:
                    terminal.focus_input()
                    await pilot.pause()
                strips = app.hub._compositor.render_strips()
                top = strips[prompt.region.y].crop(prompt.region.x, prompt.region.right)
                assert top.text.startswith("╭") and top.text.endswith("╮")
                assert any("─" in segment.text and segment.style.color == Color.parse(ink)
                           for segment in top)


@pytest.mark.parametrize("state", ("ok", "stale"))
async def test_projected_pool4_share_rate_fits_owner_size_without_detail(state):
    from maxpane_dashboard.data import surfboard as projection

    # Public live values retain their real precision; a supplied 24h change
    # covers the border direction independently of the quote source.
    raw = dict(pool4_vault_assets=1795886.4737732294, pool4_total_supply=4143519.145292,
               pool4_network="MAINNET", pool4_as_of_hhmm="01:04",
               pool4_price_usd=7.878357502256693, pool4_share_price=1.3029864737732294,
               imd_change_24h_pct=1.4)
    families = {name: dict(state=state, read_ts=STAMP)
                for name in ("pool4", "market")}
    payload = hub_payload()
    card = next(c for c in projection.cards(raw, {}, now=STAMP, family_sources=families)
                if c["key"] == "pool4")
    payload["surfboard_cards"] = [card if c["key"] == "pool4" else c
                                  for c in payload["surfboard_cards"]]
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app.hub.query_one(SurfboardRack).focus_card("pool4")
        await pilot.pause()
        assert not app.hub.query("#surfboard-detail")
        pool4 = app.hub.query_one("#surfboard-card-pool4")
        footer = app.hub._compositor.render_strips()[pool4.region.bottom - 1].crop(
            pool4.region.x, pool4.region.right)
        assert footer.text == "╰─ 1 sIMD = 1.30 IMD ─╯"
        assert "‹ widen" not in str(pool4.border_title)


async def test_dynamic_detail_is_removed_and_terminal_fills_center_after_focus_and_refresh():
    payload = hub_payload()
    for card in payload['surfboard_cards']:
        card['detail'] = 'DYNAMIC DETAIL MUST NOT APPEAR ' + 'long prose ' * 100
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        terminal = app.hub.query_one(SurfboardTerminal)
        terminal.command_input.value = 'find retained draft'
        terminal.add_reply('retained reply')
        for width, focused in ((149, 'announce'), (180, 'agent'), (148, 'board')):
            await pilot.resize_terminal(width, 45)
            app.hub.query_one(SurfboardRack).focus_card(focused)
            await app.hub._do_refresh()
            await pilot.pause()
            assert not app.hub.query('#surfboard-detail')
            assert not app.hub.query('#surfboard-center')
            visible = '\n'.join(strip.text for strip in app.hub._compositor.render_strips())
            assert 'DYNAMIC DETAIL' not in visible and 'long prose' not in visible
            assert 'retained reply' in visible
            assert terminal.command_input.value == 'find retained draft'
            assert terminal.region.bottom == app.hub.query_one(SurfboardRack).content_region.bottom
            assert terminal.query_one('#surfboard-terminal-footer').region.bottom < terminal.region.bottom


async def test_protocol_fleet_and_four_agent_seats_have_expected_positions():
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        rack = app.hub.query_one(SurfboardRack)
        agent = rack.query_one('#surfboard-card-agent')
        protocol = rack.query_one('#surfboard-card-protocol')
        fleet = rack.query_one('#surfboard-card-board')
        tokens = rack.query_one('#surfboard-card-swarm-tokens')
        work = rack.query_one('#surfboard-card-work')
        bay = rack.query_one('#surfboard-card-agent-2')
        oracles = rack.query_one('#surfboard-card-oracles')
        pool4 = rack.query_one('#surfboard-card-pool4')
        assert tokens.region.y == fleet.region.y
        assert oracles.region.y == pool4.region.y == work.region.y == protocol.region.y
        assert oracles.region.right < pool4.region.x
        assert pool4.region.right < protocol.region.x
        assert work.region.y == rack.query_one('#surfboard-card-swarm').region.y
        assert rack.query_one('#surfboard-card-swarm').region.right < work.region.x
        assert work.region.right < oracles.region.x
        assert agent.region.x == fleet.region.x
        assert bay.region.x == tokens.region.x and bay.region.y == agent.region.y
        assert bay.can_focus and bay.data['destination'] is None
        assert not rack.query('#surfboard-card-earnings')


@pytest.mark.parametrize("width", (140, 149))
async def test_web_terminal_footer_and_prompt_fit_inside_the_three_row_span(width):
    from textual.widgets import RichLog

    app = HubHarness(hub_payload())
    async with app.run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        terminal = app.hub.query_one(SurfboardTerminal)
        footer = terminal.query_one("#surfboard-terminal-footer")
        log = terminal.query_one(RichLog)
        command = terminal.command_input
        assert log.region.height >= 3
        assert log.region.bottom <= command.region.y < footer.region.y
        assert footer.region.bottom < terminal.region.bottom
        assert command.region.right <= terminal.content_region.right
        strips = app.hub._compositor.render_strips()
        visible = "\n".join(strip.crop(footer.region.x, footer.region.right).text
                            for strip in strips[footer.region.y:footer.region.bottom])
        for field in ("$IMD", "$33.69M", "$1B goal", "189.1B", "tokens", "updated"):
            assert field in visible
        assert "‹ widen" not in visible


async def test_served_event_metadata_reaches_reference_rows_and_enriches_in_place():
    from maxpane_dashboard.data import surfboard as projection
    from tests.data.test_surfboard import capture
    from textual.widgets import RichLog

    raw=capture('event_parity')
    normalized=projection.normalize_overview(raw)
    payload=hub_payload()
    payload['surfboard_events']=normalized['events']
    payload['surfboard_footer']['as_of']=raw['at']/1000
    app=HubHarness(payload)
    async with app.run_test(size=(149,45)) as pilot:
        await pilot.pause()
        terminal=app.hub.query_one(SurfboardTerminal)
        text='\n'.join(strip.text for strip in app.hub._compositor.render_strips())
        for expected in ('job     deployer     deployed     Slabs · chain 4663',
                         'job     publisher    hosted', 'job     verifier     onchain',
                         'job     swarm        completed    Fee Trade 4% · 1 step',
                         'joined  agent #961   awake'):
            assert expected in text
        assert '19 seats · back after' in text
        terminal.add_reply('metadata enrichment should stay above this reply')
        launch=next(row for row in raw['events'] if row['kind']=='launch')
        launch['token']='Slabs updated'
        terminal.update_data(surfboard_events=projection.normalize_overview(raw)['events'])
        await pilot.pause()
        rows=[line.text for line in terminal.query_one(RichLog).lines]
        assert len(rows)==len(normalized['events'])+1
        assert rows[-1]=='metadata enrichment should stay above this reply'
        assert sum('Slabs updated' in row for row in rows)==1


async def _render(payload, size):
    app = HubHarness(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        screen = app.hub
        viewport = screen.query_one("#surfboard-viewport")
        rack = screen.query_one(SurfboardRack)
        terminal = screen.query_one(SurfboardTerminal)
        cards = list(rack.query(SurfboardCard))
        strips = screen._compositor.render_strips()
        lines = ["".join(segment.text for segment in strip) for strip in strips]
        text = "\n".join(lines)
        card_regions = {card.key: card.region for card in cards}
        card_text = {card.key: "\n".join(
            strip.crop(card.region.x, card.region.right).text
            for strip in strips[max(0, card.region.y):card.region.bottom]) for card in cards}
        clipped = []
        for card in cards:
            if "‹" in str(card.border_title):
                clipped.append(card.key)
        bar = screen.query_one(StatusBar)
        right = bar.query_one("#status-right")
        return dict(text=text, size=size, cards=card_regions, card_text=card_text,
                    terminal=terminal.region, rack=rack.region,
                    horizontal=viewport.show_horizontal_scrollbar,
                    vertical=viewport.show_vertical_scrollbar,
                    clipped=clipped, status_whole=right.region.right <= size[0],
                    heights={card.key: card.region.height for card in cards},
                    widths={card.key: card.region.width for card in cards})


@pytest.mark.parametrize("width", (140, 149))
async def test_all_cards_keep_equal_whole_row_heights_when_resized(width):
    app = HubHarness(hub_payload())
    async with app.run_test(size=(width, 45)) as pilot:
        for height in (45, 46, 47, 48, 35, 34, 55, 45):
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            cards = list(app.hub.query(SurfboardCard))
            assert len({card.region.height for card in cards}) == 1
            assert cards[0].region.height >= 7
            rows = sorted({(card.region.y, card.region.bottom) for card in cards})
            assert len(rows) == 4
            assert [start - end for (_, end), (start, _) in zip(rows, rows[1:])] == [1, 3, 1]
            terminal = app.hub.query_one(SurfboardTerminal)
            assert terminal.region.y == rows[1][0]
            assert terminal.region.bottom == app.hub.query_one(SurfboardRack).content_region.bottom
            assert terminal.region.bottom >= rows[-1][1]
            footer = terminal.query_one("#surfboard-terminal-footer")
            assert footer.region.bottom < terminal.region.bottom


@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
async def test_owner_size_preserves_all_twelve_slots_and_three_row_terminal(kind):
    r = await _render(hub_payload(kind), (149, 45))
    assert not r["horizontal"] and not r["vertical"] and not r["clipped"], r
    assert r["status_whole"], r
    assert len(r["cards"]) == 12
    assert len({region.y for region in r["cards"].values()}) == 4
    assert len({r["cards"][key].y for key in ("announce", "swarm", "work", "oracles", "pool4", "protocol")}) == 1
    assert r["terminal"].y == r["cards"]["board"].y == r["cards"]["swarm-tokens"].y
    assert r["terminal"].bottom == r["rack"].bottom
    assert r["cards"]["agent-3"].bottom == r["cards"]["agent-4"].bottom <= r["terminal"].bottom
    assert r["cards"]["board"].right < r["terminal"].x < r["terminal"].right < r["cards"]["swarm-tokens"].x
    assert sorted(r["cards"], key=lambda key: (r["cards"][key].y, r["cards"][key].x)) == [
        "announce", "swarm", "work", "oracles", "pool4", "protocol",
        "board", "swarm-tokens", "agent", "agent-2", "agent-3", "agent-4"]
    for title in ("ONCHAIN FEED", "BUILT BY SWARM", "AGENT", "FLEET", "ORACLES", "POOL4", "PROTOCOL",
                  "TOKENS", "WIP", "EMPTY SEAT", "type in"):
        assert title in r["text"], (title, r["text"])


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
@pytest.mark.parametrize("width", boundary_set(SURFBOARD_FULL_LAYOUT_COLUMNS, 110, 160, 143))
async def test_width_boundary_reserves_six_columns_even_with_vertical_scrolling(kind, width):
    r = await _render(hub_payload(kind), (width, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    assert r["horizontal"] == (width < SURFBOARD_FULL_LAYOUT_COLUMNS), r
    assert ("‹ widen" in r["text"].splitlines()[0]) == r["horizontal"], r
    assert len({region.y for region in r["cards"].values()}) == 4
    if width >= SURFBOARD_FULL_LAYOUT_COLUMNS:
        assert not r["clipped"] and r["status_whole"], r


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
@pytest.mark.parametrize("height", boundary_set(SURFBOARD_FULL_LAYOUT_ROWS, 25, 55))
async def test_height_boundary_keeps_card_content_or_advertises_scroll(kind, height):
    payload = hub_payload(kind)
    r = await _render(payload, (SURFBOARD_FULL_LAYOUT_COLUMNS, height))
    assert r["vertical"] == (height < SURFBOARD_FULL_LAYOUT_ROWS), r
    assert ("‹ taller" in r["text"].splitlines()[0]) == r["vertical"], r
    assert not r["horizontal"] and not r["clipped"] and r["status_whole"], r
    assert all(value >= 7 for value in r["heights"].values()), r
    if height >= SURFBOARD_FULL_LAYOUT_ROWS:
        for card in payload["surfboard_cards"][:8]:
            if card["key"] == "swarm-tokens":
                text = r["card_text"]["swarm-tokens"]
                assert "LAST 24h" in text
                if kind != "unavailable":
                    assert card["secondary"] in text and "24h" in text
                expected = ('—',) if kind == 'unavailable' else ('SFPT', 'RAI', 'TDEMO', '↑', '↓')
                assert all(word in text for word in expected), r
                continue
            if card["key"] == "announce":
                text=r["card_text"]["announce"]
                assert " LATEST " in text
                if kind == "unavailable":
                    assert "—" in text and "unavailable" not in text
                else:
                    assert "You can now" in text and "deploy via the" in text and "..." in text
                    assert card["secondary"].removesuffix(" replies") in text
                continue
            if card["key"] == "board":
                text = r["card_text"]["board"]
                assert "TOP AGENTS" in text
                if kind == "unavailable":
                    assert "—" in text and "unavailable" not in text
                else:
                    assert text.count("★") == 3
                    for row in card['top_agents']:
                        assert str(row['token_id']) in text
                        expected_count = {99999999: '100.0M', 9999999: '10.0M', 999999: '1000.0K'}.get(row['accepted'], f"{row['accepted']:,}")
                        assert expected_count in text
                continue
            if card["key"] == "oracles":
                text = r["card_text"]["oracles"]
                assert "ASSESSING" in text
                if kind == "unavailable":
                    assert '—' in text
                elif kind == "stress":
                    assert "╶╮ ╭─╮╭─╮" in text
                else:
                    assert "╶─┐" in text
                assert (card['secondary'] if kind != 'unavailable' else '—') in text
                continue
            if card["key"] == "protocol":
                text = r["card_text"]["protocol"]
                assert " STATS " in text, r
                assert all(label in text for label in ("burned", "rewarded", "fees")), r
                assert "★" not in text and ":" not in text, r
                bottom = next(line for line in text.splitlines() if "└" in line)
                assert not bottom[bottom.index("└")+1:bottom.index("┘")].strip("─ "), r
                continue
            if card["key"] == "pool4":
                text = r["card_text"]["pool4"]
                assert " IMD PRICE " in text and "USD" in text, r
                expected = (("╶─┐ ╭─╮╭─╮", "  │ ╰─┤│ │", "  ╵•╶─╯╰─╯")
                            if kind in ("normal", "wide") else ('—' if kind == 'unavailable' else card["primary"],))
                assert all(row in text for row in expected), r
                continue
            if card["key"] == "agent":
                text = r["card_text"]["agent"]
                assert " SEAT " in text, r
                if kind == 'unavailable':
                    assert '—' in text and 'unavailable' not in text
                    continue
                expected = (("╭─╮" * 5, "╰─┤" * 5, "╶─╯" * 5) if kind == "stress" else
                            ("╷ ╷╶─╮╭─╮", "╰─┤┌─┘│ │", "  ╵╰─╴╰─╯") if kind in ("normal", "wide") else
                            (card["primary"],))
                assert all(row in text for row in expected), r
                assert card["secondary"].removesuffix(" slots") in text, r
                continue
            if card["key"] == "swarm":
                text = r["card_text"]["swarm"]
                assert "AGENTS" in text and "AGENTS ONLINE" not in text, r
                expected = ("╭─╮╭─╴╶─╮", "├─┤├─╮ ─┤", "╰─╯╰─╯╶─╯") if kind in ("normal", "wide") else ('—' if kind == 'unavailable' else card["primary"],)
                assert all(row in text for row in expected), r
                if kind != 'unavailable':
                    assert card["secondary"] in text, r
                continue
            assert card["primary"] in r["card_text"][card["key"]], (card, r)
            assert card["secondary"] in r["card_text"][card["key"]], (card, r)


async def test_width_pin_is_the_measured_scroll_transition():
    below = await _render(hub_payload(), (SURFBOARD_FULL_LAYOUT_COLUMNS - 1, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    at = await _render(hub_payload(), (SURFBOARD_FULL_LAYOUT_COLUMNS, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    assert below["horizontal"] and not at["horizontal"], (below, at)
    assert "‹ widen" in below["text"].splitlines()[0]
    assert "‹ widen" not in at["text"].splitlines()[0]


async def test_height_pin_is_the_measured_scroll_transition():
    below = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    at = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS))
    assert below["vertical"] and not at["vertical"], (below, at)
    assert "‹ taller" in below["text"].splitlines()[0]
    assert "‹ taller" not in at["text"].splitlines()[0]


async def test_translated_side_labels_match_footer_gray_in_three_line_gap_above_agent_seats():
    from rich.cells import cell_len
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for height in (45, 37, 35, 47, 48, 45):
            await pilot.resize_terminal(149, height)
            await pilot.pause()
            rack = app.hub.query_one(SurfboardRack)
            strips = app.hub._compositor.render_strips()
            news = rack.query_one('#surfboard-card-announce')
            footer = strips[news.region.bottom - 1].crop(news.region.x, news.region.right)
            label_ink = next(segment.style.color for segment in footer if 'SIGNALS' in segment.text)
            for word, above, below in [('キープ', 'board', 'agent'),
                                       ('ビルディング', 'swarm-tokens', 'agent-2')]:
                card = rack.query_one(f'#surfboard-card-{above}')
                agent = rack.query_one(f'#surfboard-card-{below}')
                assert agent.region.y - card.region.bottom == 3
                gap = [strip.crop(card.region.x, card.region.right) for strip in
                       strips[card.region.bottom:agent.region.y]]
                assert [line.text.strip() for line in gap] == ['', word, '']
                line = gap[1]
                assert abs(cell_len(line.text[:line.text.index(word)]) -
                           (card.region.width - cell_len(word)) / 2) <= .5
                assert any(segment.style.color == label_ink and not segment.style.bold
                           for segment in line if word in segment.text)
                assert sum(word in strip.text for strip in strips) == 1
            terminal = rack.query_one(SurfboardTerminal)
            assert terminal.region.y == rack.query_one('#surfboard-card-board').region.y
            assert terminal.region.bottom == rack.content_region.bottom


@pytest.mark.parametrize('kind', ['normal', 'stress'])
async def test_protocol_full_supply_footer_fits_at_owner_size(kind):
    rendered = await _render(hub_payload(kind), (149, 45))
    expected = '0.47% burned' if kind == 'normal' else '17.40% burned'
    assert expected in rendered['card_text']['protocol']
    assert 'protocol' not in rendered['clipped']


@pytest.mark.parametrize('size', [(146, 37), (149, 45), (180, 45)])
@pytest.mark.parametrize('kind', ['normal', 'stress'])
async def test_protocol_inset_matches_tokens_width_without_losing_stats(size, kind):
    rendered = await _render(hub_payload(kind), size)
    headers = [next(line for line in rendered['card_text'][key].splitlines() if '┌' in line)
               for key in ('protocol', 'swarm-tokens')]
    assert headers[0].index('┌') == headers[1].index('┌')
    assert headers[0].index('┐') == headers[1].index('┐')
    assert 'protocol' not in rendered['clipped']
    text = rendered['card_text']['protocol']
    expected = ['1M', '100k', '10k'] if kind == 'stress' else ['33k', '6k', '4k']
    unit_columns = []
    for label, value in zip(('burned', 'rewarded', 'fees'), expected):
        row = next(line for line in text.splitlines() if label in line)
        assert value in row and 'IMD' in row and '…' not in row
        assert row[headers[0].index('┌') + 1:].startswith(' ' + label)
        unit_columns.append(row.index('IMD'))
    assert len(set(unit_columns)) == 1


@pytest.mark.parametrize('size', [(149, 45), (180, 45)])
async def test_rack_columns_share_width_equally(size):
    rendered = await _render(hub_payload(), size)
    widths = list(rendered['widths'].values())
    # Whole terminal cells may leave one extra cell in a fractional track.
    assert max(widths) - min(widths) <= 1
    assert not rendered['clipped']


async def test_boardroom_title_is_centered_muted_after_refresh_and_resize():
    from rich.color import Color
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for width in (149, 180, 143):
            await pilot.resize_terminal(width, 34 if width == 143 else 45)
            await app.hub._do_refresh()
            await pilot.pause()
            row = app.hub._compositor.render_strips()[0]
            text = row.text.strip()
            assert text.startswith('IMD BOARDROOM')
            assert ('‹ widen' in text) == (width < SURFBOARD_FULL_LAYOUT_COLUMNS)
            assert abs(row.text.index(text) - (width - len(text)) / 2) <= .5
            ink = next(segment.style.color for segment in row if 'IMD BOARDROOM' in segment.text)
            card = app.hub.query_one('#surfboard-card-announce')
            card_title = app.hub._compositor.render_strips()[card.region.y].crop(card.region.x, card.region.right)
            title_ink = next(seg.style.color for seg in card_title if 'ONCHAIN FEED' in seg.text)
            assert ink == title_ink
            assert ink != Color.parse(app.get_css_variables()['accent'])
