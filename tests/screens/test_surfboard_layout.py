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


@pytest.mark.parametrize('themed', [False, True])
async def test_boardroom_heading_contains_navigation_and_preserves_content_geometry(monkeypatch, themed):
    if not themed:
        monkeypatch.setattr(HubHarness, 'CSS_PATH', [])
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for width, height, card_height, terminal_y, terminal_height in (
            (149, 45, 9, 12, 31), (143, 37, 7, 10, 25), (149, 45, 9, 12, 31),
        ):
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            heading = app.hub.query_one('#surfboard-title')
            terminal = app.hub.query_one(SurfboardTerminal)
            cards = list(app.hub.query(SurfboardCard))
            assert {card.region.height for card in cards} == {card_height}
            assert (terminal.region.y, terminal.region.height) == (terminal_y, terminal_height)
            assert heading.region.y == 0
            assert not app.hub.query('#surfboard-navigation')
            rows = app.hub._compositor.render_strips()
            heading_text = rows[0].text
            left = '↑ ↓ ← → to navigate cards'
            title = 'IMD BOARDROOM'
            right = '↵ to open selected dashboard'
            assert heading_text.index(left) < heading_text.index(title) < heading_text.index(right)
            assert 'arrow keys' not in heading_text
            empty_card = app.hub.query_one('#surfboard-card-agent-4', SurfboardCard)
            footer = rows[empty_card.region.bottom - 1]
            footer_ink = next(iter(footer.crop(footer.text.index('Identity.md'), footer.text.index('Identity.md') + 1))).style.color
            for hint in (left, right):
                hint_ink = next(iter(rows[0].crop(heading_text.index(hint), heading_text.index(hint) + 1))).style.color
                assert hint_ink == footer_ink
            left_gap = heading_text.index(title) - (heading_text.index(left) + len(left))
            right_gap = heading_text.index(right) - (heading_text.index(title) + len(title))
            assert abs(left_gap - right_gap) <= 1
            assert abs(heading_text.index(title) - (width - len(title)) / 2) <= .5
            assert left not in rows[terminal_y - 1].text
            assert all('WORKFLOWS [g]' not in row.text for row in rows)
            assert sum('IMD BOARDROOM' in row.text for row in rows) == 1


@pytest.mark.parametrize('size', [(146, 37), (149, 45)])
async def test_fleet_stats_acceptance_and_duration_survive_refresh(size):
    payload = hub_payload()
    app = HubHarness(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-board', SurfboardCard)
        def painted():
            return '\n'.join(strip.crop(card.region.x, card.region.right).text for strip in
                             app.hub._compositor.render_strips()[card.region.y:card.region.bottom])
        output = painted()
        assert all(text in output for text in ('STATS', 'tokens', '189.1B', 'jobs', '14,206',
                                              'capacity', '1,500', '95.84%', 'worked 1y 32w 3d'))
        assert 'top model' not in output and 'TOP AGENTS' not in output
        bottom = next(line for line in output.splitlines() if '└' in line)
        assert '┘' in bottom and '95.84%' in bottom
        facts = next(row for row in payload['surfboard_cards'] if row['key'] == 'board')['fleet_summary']
        facts.update(tokens=5000000, jobs=12, capacity=2000, accept_rate=96.25)
        await app.hub._do_refresh()
        await pilot.pause()
        output = painted()
        assert '5.0M' in output and '96.25%' in output
        assert '2,000' in output and 'worked 1y 32w 3d' in output
        assert card.data['destination'] == 'board'


@pytest.mark.parametrize("signals", [0, 1, 4, 9, 11, None])
async def test_news_signal_footer_counts_segments_and_fills_width_on_resize(signals):
    payload = hub_payload()
    news = next(card for card in payload["surfboard_cards"] if card["key"] == "announce")
    news.update(numerator=signals, denominator=11)
    app = HubHarness(payload)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for width in (149, 180, 140, 149):
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            card = app.hub.query_one("#surfboard-card-announce", SurfboardCard)
            footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(
                card.region.x, card.region.right)
            label = footer.text.strip('╰╯─ ')
            assert abs(footer.text.index(label) - (card.region.width - len(label)) / 2) <= .5
            if signals is None:
                assert label == '0 SIGNALS'
                assert "▰" not in footer.text and "▱" not in footer.text
                continue
            cells = card.region.width - 6 - len(f'{signals} SIGNALS') - 1
            if signals == 0 or signals > cells:
                assert label == f'{signals} SIGNALS'
                assert "▰" not in footer.text
                continue
            bar = "▰" * signals + "▱" * (cells - signals)
            assert footer.text == f"╰─ {signals} SIGNALS {bar} ─╯"
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
        for count, total, displayed in [(24, 30, 24), (3, 11, 3), (None, None, 3), (0, 11, 0)]:
            card.set_data(dict(primary="Latest post", secondary="7 new", numerator=count, denominator=total))
            await pilot.pause()
            footer = app.hub._compositor.render_strips()[card.region.bottom - 1].crop(
                card.region.x, card.region.right).text
            if count == 24:
                assert "24 SIGNALS" in footer and "▰" not in footer
            else:
                assert footer.count("▰") == displayed
                assert "‹ widen" not in str(card.border_title)
                assert f"{displayed} SIGNALS" in footer


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
                         if "189.1B" in segment.text)
            reply = next(segment for strip in strips for segment in strip
                         if "palette reply" in segment.text)
            assert value.style.bgcolor == Color.parse(theme.background)
            assert value.style.color == Color.parse(app.get_css_variables()['foreground'])
            assert value.style.dim is False
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
        assert footer.text == "╰─ 1 sIMD = 1.303 IMD ─╯"
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


async def test_nft_fleet_and_four_agent_seats_have_expected_positions():
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        rack = app.hub.query_one(SurfboardRack)
        agent = rack.query_one('#surfboard-card-agent')
        nft = rack.query_one('#surfboard-card-surf-nft')
        fleet = rack.query_one('#surfboard-card-board')
        tokens = rack.query_one('#surfboard-card-swarm-tokens')
        work = rack.query_one('#surfboard-card-work')
        bay = rack.query_one('#surfboard-card-agent-2')
        oracles = rack.query_one('#surfboard-card-oracles')
        pool4 = rack.query_one('#surfboard-card-pool4')
        assert tokens.region.y == nft.region.y
        assert oracles.region.y == pool4.region.y == work.region.y == fleet.region.y
        assert oracles.region.right < pool4.region.x
        assert pool4.region.right < fleet.region.x
        assert fleet.region.x == tokens.region.x and fleet.region.bottom < tokens.region.y
        assert work.region.y == rack.query_one('#surfboard-card-swarm').region.y
        assert rack.query_one('#surfboard-card-swarm').region.right < work.region.x
        assert work.region.right < oracles.region.x
        assert agent.region.x == nft.region.x
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
        return dict(text=text, title=strips[screen.query_one("#surfboard-title").region.y].text,
                    size=size, cards=card_regions, card_text=card_text,
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
    assert len({r["cards"][key].y for key in ("announce", "swarm", "work", "oracles", "pool4", "board")}) == 1
    assert r["terminal"].y == r["cards"]["surf-nft"].y == r["cards"]["swarm-tokens"].y
    assert r["terminal"].bottom == r["rack"].bottom
    assert r["cards"]["agent-3"].bottom == r["cards"]["agent-4"].bottom <= r["terminal"].bottom
    assert r["cards"]["surf-nft"].right < r["terminal"].x < r["terminal"].right < r["cards"]["swarm-tokens"].x
    assert sorted(r["cards"], key=lambda key: (r["cards"][key].y, r["cards"][key].x)) == [
        "announce", "swarm", "work", "oracles", "pool4", "board",
        "surf-nft", "swarm-tokens", "agent", "agent-2", "agent-3", "agent-4"]
    for title in ("ONCHAIN FEED", "BUILT BY SWARM", "AGENT", "FLEET", "ORACLES", "POOL4", "NFTS",
                  "TOKENS", "WIP", "EMPTY SEAT", "type in"):
        assert title in r["text"], (title, r["text"])


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ("normal", "stress", "unavailable", "wide"))
@pytest.mark.parametrize("width", boundary_set(SURFBOARD_FULL_LAYOUT_COLUMNS, 110, 160, 143))
async def test_width_boundary_reserves_six_columns_even_with_vertical_scrolling(kind, width):
    r = await _render(hub_payload(kind), (width, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    # A short viewport needs one real scrollbar cell; tall viewports reserve none.
    assert r["horizontal"] == (width < SURFBOARD_FULL_LAYOUT_COLUMNS + 1), r
    assert ("‹ widen" in r["title"]) == r["horizontal"], r
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
    assert ("‹ taller" in r["title"]) == r["vertical"], r
    assert r["horizontal"] == (height < SURFBOARD_FULL_LAYOUT_ROWS), r
    assert not r["clipped"] and r["status_whole"], r
    assert all(value >= 7 for value in r["heights"].values()), r
    if height >= SURFBOARD_FULL_LAYOUT_ROWS:
        for card in payload["surfboard_cards"][:8]:
            text = r["card_text"][card["key"]]
            lines = text.splitlines()
            top = next(index for index, line in enumerate(lines) if '┌' in line)
            left, right = lines[top].index('┌'), lines[top].index('┐')
            body = [line[left + 1:right] for line in lines[top + 1:top + 4]]
            if card["key"] == "swarm-tokens":
                text = r["card_text"]["swarm-tokens"]
                assert "LATEST" in text
                if kind != "unavailable":
                    assert card["secondary"] in text and "24h" in text
                if kind == 'unavailable':
                    assert not any(row.strip() for row in body), r
                else:
                    assert all(word in text for word in ('SFPT', 'RAI', 'TDEMO', '↑', '↓')), r
                continue
            if card["key"] == "announce":
                text=r["card_text"]["announce"]
                assert " LATEST " in text
                if kind == "unavailable":
                    assert not any(row.strip() for row in body) and "unavailable" not in text
                else:
                    assert "You can now" in text and "deploy via the" in text and "..." in text
                    assert card["secondary"].removesuffix(" replies") in text
                continue
            if card["key"] == "board":
                text = r["card_text"]["board"]
                assert "STATS" in text
                assert all(label in text for label in ('tokens', 'jobs'))
                assert 'capacity' in text or 'cap.' in text
                assert 'top model' not in text and 'TOP AGENTS' not in text
                if kind == "unavailable":
                    assert [row.split() for row in body] == [['tokens', '0'], ['jobs', '0'], ['capacity', '0']]
                    assert '0.00%' in text and "unavailable" not in text
                else:
                    assert ('100.00%' if kind == 'stress' else '95.84%') in text
                continue
            if card["key"] == "oracles":
                text = r["card_text"]["oracles"]
                assert "JOBS" in text
                if kind == "unavailable":
                    assert not any(row.strip() for row in body)
                elif kind == "stress":
                    assert "╶╮ ╭─╮╭─╮" in text
                else:
                    assert "╶─┐" in text
                caption = '0 agents' if card['secondary'] == '— agents' else card['secondary']
                if kind == 'unavailable':
                    assert not lines[top + 4][left + 1:right].strip('─ ')
                    assert '0 chains' in text
                else:
                    assert caption in text
                continue
            if card["key"] == "surf-nft":
                text = r["card_text"]["surf-nft"]
                assert "COLLECTIONS" in text and ("build" in text or "bld" in text) and "open" in text, r
                continue
            if card["key"] == "pool4":
                text = r["card_text"]["pool4"]
                assert " IMD PRICE " in text and "USD" in text, r
                if kind == 'unavailable':
                    assert not any(row.strip() for row in body), r
                else:
                    expected = (("╶─┐ ╭─╮╭─╮", "  │ ╰─┤│ │", "  ╵•╶─╯╰─╯")
                                if kind in ("normal", "wide") else (card["primary"],))
                    assert all(row in text for row in expected), r
                continue
            if card["key"] == "agent":
                text = r["card_text"]["agent"]
                assert " SEAT " in text, r
                if kind == 'unavailable':
                    assert not any(row.strip() for row in body) and 'unavailable' not in text
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
                if kind == 'unavailable':
                    assert not any(row.strip() for row in body), r
                else:
                    expected = ("╭─╮╭─╴╶─╮", "├─┤├─╮ ─┤", "╰─╯╰─╯╶─╯") if kind in ("normal", "wide") else (card["primary"],)
                    assert all(row in text for row in expected), r
                    assert card["secondary"] in text, r
                continue
            assert card["primary"] in r["card_text"][card["key"]], (card, r)
            assert card["secondary"] in r["card_text"][card["key"]], (card, r)


@pytest.mark.parametrize('short', [False, True])
async def test_width_pin_is_the_measured_scroll_transition(short):
    height = SURFBOARD_FULL_LAYOUT_ROWS - short
    width = SURFBOARD_FULL_LAYOUT_COLUMNS + short
    below = await _render(hub_payload(), (width - 1, height))
    at = await _render(hub_payload(), (width, height))
    assert below["horizontal"] and not at["horizontal"], (below, at)
    assert "‹ widen" in below["title"]
    assert "‹ widen" not in at["title"]


async def test_height_pin_is_the_measured_scroll_transition():
    below = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS - 1))
    at = await _render(hub_payload(), (149, SURFBOARD_FULL_LAYOUT_ROWS))
    assert below["vertical"] and not at["vertical"], (below, at)
    assert "‹ taller" in below["title"]
    assert "‹ taller" not in at["title"]


async def test_scrollbars_and_hints_return_after_repeated_short_tall_resizes():
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for width, height, horizontal, vertical in [
            (149, 45, False, False), (143, 36, True, True),
            (143, 37, False, False), (143, 36, True, True),
            (143, 37, False, False), (142, 45, True, False),
            (149, 45, False, False),
        ]:
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            viewport = app.hub.query_one('#surfboard-viewport')
            title = app.hub._compositor.render_strips()[app.hub.query_one('#surfboard-title').region.y].text
            assert viewport.show_horizontal_scrollbar == horizontal, (width, height)
            assert viewport.show_vertical_scrollbar == vertical, (width, height)
            assert ('‹ widen' in title) == horizontal
            assert ('‹ taller' in title) == vertical
            if horizontal:
                viewport.scroll_to(x=viewport.max_scroll_x, animate=False, force=True)
                await pilot.pause()
                fleet = app.hub.query_one('#surfboard-card-board')
                assert fleet.region.right <= viewport.scrollable_content_region.right


async def test_translated_side_labels_are_muted_green_in_three_line_gap_above_agent_seats():
    from rich.cells import cell_len
    from rich.color import Color
    from textual.filter import dim_color
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for height in (45, 37, 35, 47, 48, 45):
            await pilot.resize_terminal(149, height)
            await pilot.pause()
            rack = app.hub.query_one(SurfboardRack)
            strips = app.hub._compositor.render_strips()
            for word, above, below in [('キープ', 'surf-nft', 'agent'),
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
                caption = next(segment for segment in line if word in segment.text)
                assert caption.style.color == dim_color(
                    caption.style.bgcolor, Color.parse(app.get_css_variables()['foreground']))
                assert not caption.style.bold
                assert sum(word in strip.text for strip in strips) == 1
            terminal = rack.query_one(SurfboardTerminal)
            assert terminal.region.y == rack.query_one('#surfboard-card-surf-nft').region.y
            assert terminal.region.bottom == rack.content_region.bottom


@pytest.mark.parametrize('kind', ['normal', 'stress'])
async def test_nft_card_footer_shows_build_open_counts_at_owner_size(kind):
    rendered=await _render(hub_payload(kind),(149,45))
    text=rendered['card_text']['surf-nft']
    assert 'partial' not in text
    footer=text.splitlines()[-1].strip('╰╯─ ')
    assert footer == ('3 build · 15 open' if kind == 'normal' else '100bld · 999open')
    inset_footer=next(line for line in text.splitlines() if '└' in line)
    assert ('3 building' if kind == 'normal' else '100 building') in inset_footer
    assert 'surf-nft' not in rendered['clipped']



@pytest.mark.parametrize('size', [(146,37),(149,45),(180,45)])
@pytest.mark.parametrize('kind', ['normal','stress'])
async def test_nft_inset_matches_tokens_padding_without_losing_counts(size,kind):
    rendered=await _render(hub_payload(kind),size)
    headers=[next(line for line in rendered['card_text'][key].splitlines() if '┌' in line)
             for key in ('surf-nft','swarm-tokens')]
    assert headers[0].index('┌')==headers[1].index('┌')
    assert len(headers[0])-headers[0].index('┐')==len(headers[1])-headers[1].index('┐')
    assert 'surf-nft' not in rendered['clipped']
    assert any(label in rendered['card_text']['surf-nft'] for label in ('build','bld'))
    assert 'open' in rendered['card_text']['surf-nft']



@pytest.mark.parametrize('stylesheet', [True, False])
async def test_boardroom_uses_full_width_equal_columns_and_keeps_grid_aligned_on_resize(stylesheet):
    from rich.cells import cell_len
    class DefaultStylesHarness(HubHarness):
        CSS_PATH = None

    sizes = [(149, [24, 24, 24, 24, 24, 24]),
             (143, [23, 23, 23, 23, 23, 23]),
             (145, [23, 23, 24, 23, 23, 24]),
             (151, [24, 24, 25, 24, 24, 25]),
             (180, [29, 29, 29, 29, 29, 30]),
             (149, [24, 24, 24, 24, 24, 24])]
    app = (HubHarness if stylesheet else DefaultStylesHarness)(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for width, expected in sizes:
            await pilot.resize_terminal(width, 45)
            await pilot.pause()
            rack = app.hub.query_one(SurfboardRack)
            assert rack.region.x == 0
            assert rack.region.width == width
            for card in rack.query(SurfboardCard):
                column = card.rack_column
                assert card.region.width == expected[column], (width, card.key, card.region)
                assert card.region.x == rack.content_region.x + sum(expected[:column]) + column
                assert card.region.height == 9
                assert '‹' not in str(card.border_title)
            terminal = rack.query_one(SurfboardTerminal)
            assert terminal.region.x == rack.query_one('#surfboard-card-swarm').region.x
            assert terminal.region.right == rack.query_one('#surfboard-card-pool4').region.right
            assert terminal.region.width == sum(expected[1:5]) + 3
            assert rack.region.right == rack.query_one('#surfboard-card-board').region.right
            strips = app.hub._compositor.render_strips()
            for key, label_id, word in [('surf-nft', 'keep', 'キープ'),
                                        ('swarm-tokens', 'building', 'ビルディング')]:
                card = rack.query_one(f'#surfboard-card-{key}')
                label = rack.query_one(f'#surfboard-{label_id}')
                assert label.region.x == card.region.x
                assert label.region.width == card.region.width
                line = strips[card.region.bottom + 1].crop(card.region.x, card.region.right).text
                assert abs(cell_len(line[:line.index(word)]) -
                           (card.region.width - cell_len(word)) / 2) <= .5


async def test_boardroom_title_is_centered_muted_green_after_refresh_and_resize():
    from rich.color import Color
    from textual.filter import dim_color
    app = HubHarness(hub_payload())
    async with app.run_test(size=(149, 45)) as pilot:
        for width in (149, 180, 143):
            await pilot.resize_terminal(width, 34 if width == 143 else 45)
            await app.hub._do_refresh()
            await pilot.pause()
            heading = app.hub.query_one('#surfboard-title')
            row = app.hub._compositor.render_strips()[heading.region.y].crop(heading.region.x, heading.region.right)
            text = row.text[row.text.index('IMD BOARDROOM'):].split('↵', 1)[0].strip()
            assert ('‹ widen' in text) == app.hub.query_one('#surfboard-viewport').show_horizontal_scrollbar
            assert abs(row.text.index(text) - (heading.region.width - len(text)) / 2) <= .5
            title = next(segment for segment in row if 'IMD BOARDROOM' in segment.text)
            card = app.hub.query_one('#surfboard-card-announce')
            card_title = app.hub._compositor.render_strips()[card.region.y].crop(card.region.x, card.region.right)
            title_ink = next(seg.style.color for seg in card_title if 'ONCHAIN FEED' in seg.text)
            assert title.style.color == dim_color(
                title.style.bgcolor, Color.parse(app.get_css_variables()['foreground']))
            assert title.style.color != title_ink
            assert title.style.color != Color.parse(app.get_css_variables()['accent'])
