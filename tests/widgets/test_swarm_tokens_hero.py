"""LAUNCHES hero projection, checked through the Textual compositor."""
import time

import pytest
from rich.color import Color
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.swarm_tokens.hero import TokensHero, TokensHeroCard


@pytest.fixture(autouse=True)
def offline_colors(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("hero tests must not use the network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


@pytest.fixture
def local_clock(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setenv("TZ", "Europe/Berlin")
        time.tzset()
        yield
    time.tzset()


def payload():
    source = dict(state="ok", read_ts=1791775800.)
    return dict(
        tokens=dict(source, tracked=48, new_24h=4, chains=3),
        volume=dict(source, amount=124800., known=41, total=48),
        liquidity=dict(source, imd=12400., eth=3.8, known=43, total=48, partial=True),
        pools=dict(source, two_sided=35, one_sided=8, unknown=5, other=0),
        momentum=dict(source, rising=22, falling=14, flat=5, known=41, total=48),
        top_volume=dict(source, rows=[dict(symbol="ORBIT", volume_usd=38200),
                                     dict(symbol="BMC", volume_usd=21400),
                                     dict(symbol="RNNN", volume_usd=14800)], known=41, total=48),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield TokensHero()
    def on_mount(self):
        self.query_one(TokensHero).update_data(tokens_hero=self.data)


def painted(app, key):
    card = app.query_one(f"#hero-{key.replace('_', '-')}")
    region = card.region
    return "\n".join(strip.crop(region.x, region.right).text
                     for strip in app.screen._compositor.render_strips()[region.y:region.bottom])


async def test_approved_six_card_geometry_and_values():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(TokensHeroCard))
        assert [card.data.title for card in cards] == ["TOKENS", "VOLUME", "LIQUIDITY", "POOLS", "MOMENTUM", "TOP VOLUME"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for key, values in {
            "tokens": ("tracked", "48", "new 24h", "4", "chains", "3", "SELECTION"),
            "volume": ("kUSD / 24H", "41/48 known", "MEASURED"),
            "liquidity": ("≥12.4k IMD", "≥3.8 ETH", "43/48 known", "QUOTE ASSETS"),
            "pools": ("two-sided", "35", "one-sided", "8", "unknown", "5", "LIQUIDITY"),
            "momentum": ("rising", "22", "falling", "14", "flat", "5", "41/48 known"),
            "top_volume": ("ORBIT", "$38.2k", "BMC", "$21.4k", "RNNN", "$14.8k", "LEADERS"),
        }.items():
            output = painted(app, key)
            assert all(value in output for value in values), output
            assert all(corner in output for corner in "┌┐└┘")
        assert "other" not in painted(app, "pools")
        assert app.query_one("#hero-volume").data.digits == "124.8"
        assert "╷" in painted(app, "volume")  # Native large-digit face.


async def test_liquidity_keeps_amount_before_asset_with_separate_colors_and_padding():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, card = pilot.app, pilot.app.query_one("#hero-liquidity")
        lines = painted(app, "liquidity").splitlines()
        top = next(index for index, row in enumerate(lines) if "┌" in row)
        left, right = lines[top].index("┌"), lines[top].index("┐")
        for index, amount, asset in ((top + 1, "≥12.4k", "IMD"), (top + 2, "≥3.8", "ETH")):
            row = lines[index]
            assert row[left + 1] == row[right - 1] == " "
            assert amount + " " + asset in row
            for text, color in ((amount, Color.parse(app.get_css_variables()["foreground"]).get_truecolor()),
                                (asset, card.rich_style.color.get_truecolor())):
                for x in range(row.index(text), row.index(text) + len(text)):
                    assert app.screen.get_style_at(card.region.x + x, card.region.y + index).color.get_truecolor() == color


async def test_partial_and_stale_keep_coverage_and_their_own_clocks(local_clock):
    data = payload()
    data["volume"].update(state="partial", read_ts=1791774000.)
    data["liquidity"].update(state="stale", read_ts=1791774600., imd=None, eth=None)
    data["top_volume"].update(state="partial", read_ts=1791774000.)
    data["pools"]["other"] = 2
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "partial" not in painted(app, "volume") and "41/48 known" in painted(app, "volume")
        assert "MEASURED" in painted(app, "volume")
        assert "partial" in str(app.query_one("#hero-volume").tooltip)
        assert "stale" not in str(app.query_one("#hero-volume").tooltip)
        assert "05:00 local" in str(app.query_one("#hero-volume").tooltip)
        assert "stale" not in painted(app, "liquidity") and "43/48 known" in painted(app, "liquidity")
        assert "-- IMD" in painted(app, "liquidity") and "-- ETH" in painted(app, "liquidity")
        assert "41/48 known" in painted(app, "top_volume")
        assert "2 other" in painted(app, "pools")
        assert "05:10 local" in str(app.query_one("#hero-liquidity").tooltip)
        assert all("partial" not in painted(app, key) for key in data)



async def test_empty_selection_zero_and_unknown_are_distinct():
    data = payload()
    data["tokens"].update(tracked=0, new_24h=0, chains=0)
    data["volume"].update(amount=0, known=0, total=0)
    data["liquidity"].update(imd=0, eth=None, partial=False, known=0, total=0)
    data["top_volume"].update(rows=[], known=0, total=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "0/0 known" in painted(app, "volume")
        assert "0 IMD" in painted(app, "liquidity") and "-- ETH" in painted(app, "liquidity")
        assert "No matching" in painted(app, "top_volume") and "tokens" in painted(app, "top_volume")
        app.query_one(TokensHero).update_data(tokens_hero=None)
        await pilot.pause()
        assert all("unavailable" not in painted(app, key) for key in payload())
        assert "0/0 known" not in painted(app, "volume")


@pytest.mark.parametrize("amount,heading,face", [(0.0000000042, "USD / 24H", "4.2e-09"), (4.2, "USD / 24H", "4.2"), (12480000., "MUSD / 24H", "12.48")])
async def test_volume_scale_preserves_small_positive_values(amount, heading, face):
    data = payload()
    data["volume"]["amount"] = amount
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = pilot.app.query_one("#hero-volume")
        assert card.data.digits == face and heading in painted(pilot.app, "volume")
        if "e" in face:
            assert face in painted(pilot.app, "volume")


async def test_hostile_symbols_large_counts_and_unknown_leaders_stay_honest():
    data = payload()
    data["tokens"]["tracked"] = 123456789012345
    data["top_volume"]["rows"] = [dict(symbol="[/x]\x1b中" * 4, volume_usd=38200),
                                   dict(symbol="0x1234567890123456789012345678901234567890", volume_usd=.0000000042),
                                   dict(symbol="BMC", volume_usd=None)]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "top_volume")
        assert "1.23e+14" in painted(pilot.app, "tokens")
        assert "…" in output and "[/x]" in output
        assert "0x" not in output and "token" in output
        assert "$4.2e-09" in output
        assert any("BMC" in row and "--" in row for row in output.splitlines())
