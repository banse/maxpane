"""Production news hero records, asserted through the painted compositor."""
import pytest
from rich.color import Color
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard, SurfNewsHero


@pytest.fixture(autouse=True)
def isolated_colors(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)


def payload():
    source = dict(state="ok", read_ts=1791775800.0)
    return dict(
        announcement=dict(source, text="A new official announcement", age_s=1080),
        reply=dict(source, text="Can existing agents move over?", age_s=420),
        signals=dict(source, fired=2, watch=1, quiet=8, known=11, total=11),
        activity=dict(source, rows=[dict(age_s=360, wallet_label="dev", kind="deploy")], wallet_count=2),
        market=dict(source, price_usd=9.41, change_24h_pct=2.3, points=[9.2, 9.3, 9.41]),
        boards=dict(source, holders=812, written=1967, moves_24h=38),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"

    def __init__(self, data=None):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield SurfNewsHero()

    def on_mount(self):
        self.query_one(SurfNewsHero).update_data(surf_news_hero=self.data)


def painted(app, widget=None):
    strips = app.screen._compositor.render_strips()
    region = widget.region if widget is not None else app.screen.region
    return "\n".join(strip.crop(region.x, region.right).text for strip in strips[region.y:region.bottom])


async def test_live_payload_fills_six_equal_rack_cards():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "ANNOUNCEMENT", "LATEST REPLY", "SIGNALS", "DEV ACTIVITY", "IMD MARKET", "NFT BOARDS"]
        assert len({card.region.y for card in cards}) == 1
        assert {card.region.height for card in cards} == {9}
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for card in cards:
            text = painted(app, card)
            assert f"⊙ {card.data.title}" in text
            assert all(edge in text for edge in "┌┐└┘")
        assert "KNOWN 11/11" in painted(app, cards[2])
        assert "6m dev deploy" in painted(app, cards[3])
        assert "2 wallets" in painted(app, cards[3])
        assert "+2.3% · 24h" in painted(app, cards[4])
        assert "╭─╮ ╷ ╷╶╮" in painted(app, cards[4])
        assert "1,967" in painted(app, cards[5])
        assert "as of" in str(cards[0].tooltip)


async def test_unknown_empty_and_zero_remain_distinct():
    data = payload()
    data["announcement"]["text"] = None
    data["reply"]["text"] = None
    data["activity"]["rows"] = []
    data["signals"].update(state="unavailable", read_ts=None, fired=0, watch=0, quiet=0, known=0)
    data["boards"].update(holders=0, written=None, moves_24h=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "No posts in" in painted(app, app.query_one("#hero-announcement"))
        assert "cache" in painted(app, app.query_one("#hero-announcement"))
        assert "No replies in" in painted(app, app.query_one("#hero-reply"))
        assert "cache" in painted(app, app.query_one("#hero-reply"))
        assert "No recent" in painted(app, app.query_one("#hero-activity"))
        assert "activity" in painted(app, app.query_one("#hero-activity"))
        signals = painted(app, app.query_one("#hero-signals"))
        assert "known 0/11" in signals and "unavailable" not in signals
        assert all(any(label in line and "--" in line for line in signals.splitlines()) for label in ("fired", "watch", "quiet"))
        boards = painted(app, app.query_one("#hero-boards"))
        assert any("holders" in line and "0" in line for line in boards.splitlines())
        assert any("written" in line and "--" in line for line in boards.splitlines())
        app.query_one(SurfNewsHero).update_data(surf_news_hero=None)
        await pilot.pause()
        assert all("unavailable" not in painted(app, card) for card in app.query(NewsHeroCard))
        assert "known 0/11" in painted(app, app.query_one("#hero-signals"))


async def test_stale_badges_use_their_own_source_clock_and_keep_cached_values():
    data = payload()
    data["announcement"].update(state="stale", read_ts=1791774000.0)
    data["market"].update(state="stale", read_ts=1791774600.0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        announcement = app.query_one("#hero-announcement")
        market = app.query_one("#hero-market")
        assert "OFFICIAL" in painted(app, announcement) and "03:00" in str(announcement.tooltip)
        assert "PRICE" in painted(app, market) and "03:10" in str(market.tooltip)
        assert "18m ago" in painted(app, announcement)
        assert "+2.3% · 24h" in painted(app, market)
        strips = app.screen._compositor.render_strips()
        for card in (announcement, market):
            inset = next(strip.crop(card.region.x, card.region.right) for strip in strips[card.region.y:card.region.bottom] if "┌" in strip.text)
            edge = next(segment for segment in inset if "┌" in segment.text)
            assert edge.style.color != Color.parse(app.get_css_variables()["accent"])


@pytest.mark.parametrize("state", ["ok", "stale"])
async def test_body_palette_and_padding_follow_final_frame_without_recoloring_captions(state):
    data = payload()
    data["market"]["state"] = state
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        green = app.ansi_theme.ansi_colors[2]
        value = Color.parse(app.get_css_variables()["foreground"]).get_truecolor()
        for key in ("announcement", "reply", "signals", "activity", "market", "boards"):
            card = app.query_one(f"#hero-{key}")
            rows = painted(app, card).splitlines()
            top = next(index for index, row in enumerate(rows) if "┌" in row)
            left, right = rows[top].index("┌"), rows[top].index("┐")
            for offset, row in enumerate(rows[top + 1:top + 4], 1):
                if key != "market":
                    assert row[left + 1] == row[right - 1] == " ", (key, row)
                for x in range(left + 1, right):
                    if row[x].isspace():
                        continue
                    style = app.screen.get_style_at(card.region.x + x, card.region.y + top + offset)
                    expected = green
                    if key == "market":
                        expected = green if state == "ok" else card.rich_style.color.get_truecolor()
                    elif key in ("signals", "boards"):
                        number = card.data.stats[offset - 1][1]
                        expected = value if x >= right - 1 - len(number) else green
                    elif key == "activity" and x < left + 4:
                        expected = value
                    assert style.color.get_truecolor() == expected and not style.dim, (key, row, x, style)
            if key == "market":
                frame = app.screen.get_style_at(card.region.x + left, card.region.y + top)
                assert (frame.color == Color.parse(app.get_css_variables()["accent"])) == (state == "ok")


@pytest.mark.parametrize("price, expected", [(0.0000000042, "4.2e-09"), (0.004123, "0.004123"), (1000000000000, "1.00e+12")])
async def test_price_precision_and_large_counts_fit_without_false_zero(price, expected):
    data = payload()
    data["market"].update(price_usd=price, points=[])
    data["boards"].update(holders=123456789012345, written=987654321, moves_24h=12345678)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        market = painted(app, app.query_one("#hero-market"))
        assert expected in market and "0.00" not in market.replace(expected, "")
        boards = painted(app, app.query_one("#hero-boards"))
        assert "1.23e+14" in boards and "987.7M" in boards and "12.3M" in boards
        assert "history pending" not in market and "PRICE" in market


async def test_untrusted_preview_is_literal_and_keeps_address_copy_action():
    data = payload()
    address = "0x1234567890123456789012345678901234567890"
    data["announcement"]["text"] = "[/x] " + address + " \x1b中" * 10
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        card = app.query_one("#hero-announcement")
        output = painted(app, card)
        assert "[/x]" in output and "⧉" in output and "..." in output
        assert any(segment.style and "copy_address" in str(segment.style.meta)
                   for strip in app.screen._compositor.render_strips()[card.region.y:card.region.bottom]
                   for segment in strip.crop(card.region.x, card.region.right))
        for strip in app.screen._compositor.render_strips()[card.region.y:card.region.bottom]:
            for segment in strip.crop(card.region.x, card.region.right):
                if segment.style and "copy_address" in str(segment.style.meta):
                    assert segment.style.color == Color.parse(app.get_css_variables()["foreground"])


@pytest.mark.parametrize("width", [60, 90])
async def test_narrow_cards_fit_values_inside_frames_and_mark_truncation(width):
    data = payload()
    data["boards"].update(holders=123456789012345)
    async with Harness(data).run_test(size=(width, 20)) as pilot:
        await pilot.pause()
        app = pilot.app
        card = app.query_one("#hero-boards")
        output = painted(app, card)
        assert "…" in output
        rows = [line for line in output.splitlines() if "│" in line]
        assert all(line.count("│") in (2, 4) for line in rows)
        assert "└" in output and "┘" in output
