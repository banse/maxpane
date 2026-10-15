"""Source-aware POOL4 rack cards, asserted on the painted terminal."""
import time

import pytest
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.pool4_hero import SurfPool4RackHero


@pytest.fixture(autouse=True)
def offline_colors(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("widget tests must not use the network")
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
        price=dict(source, usd=9.410, venue="here", gap_pct=-1.20),
        rate=dict(source, imd=7.964),
        staking=dict(source, apr=8.4),
        vault=dict(source, imd=82400, simd=82400 / 7.964, holders=126,
                   holders_state="ok", holders_read_ts=1791775800.),
        bid=dict(source, status="deployed", eth=18.60, distance_pct=3.2),
        queue=dict(source, imd=7440, per_day=1200, days=6.2),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfPool4RackHero()
    def on_mount(self):
        self.query_one(SurfPool4RackHero).update_data(surf_pool4_hero=self.data)


def painted(app, key):
    region = app.query_one(f"#hero-{key}").region
    return "\n".join(strip.crop(region.x, region.right).text
                     for strip in app.screen._compositor.render_strips()[region.y:region.bottom])


async def test_approved_six_cards_preserve_equal_geometry_and_units():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["IMD PRICE", "sIMD RATE", "STAKING", "VAULT", "DOWNSIDE BID", "DRIP QUEUE"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for key, values in {
            "price": ("USD", "here -1.20%", "POOL4"),
            "rate": ("IMD", "per 1 sIMD", "EXCHANGE"),
            "staking": ("APR %", "trailing 7d", "REALISED"),
            "vault": ("IMD", "82.4k", "sIMD", "10.35k", "addresses", "126", "STAKED"),
            "bid": ("ETH", "3.20% under", "DEPLOYED"),
            "queue": ("queued", "7.44k IMD", "cap", "1.2k IMD/d", "queue", "6.2d", "RATE LIMITED"),
        }.items():
            output = painted(app, key)
            assert all(value in output for value in values), output
            assert all(corner in output for corner in "┌┐└┘")
        for key, digits in (("price", "9.410"), ("rate", "7.964"), ("staking", "8.4"), ("bid", "18.60")):
            assert app.query_one(f"#hero-{key}").data.digits == digits
            assert any(character in painted(app, key) for character in "╭╮╴╷")


async def test_no_bid_zero_balances_and_missing_values_remain_distinct():
    data = payload()
    data["bid"].update(status="none", eth=None, distance_pct=None)
    data["vault"].update(imd=0, simd=0, holders=None, holders_state="unavailable", holders_read_ts=None)
    data["queue"].update(imd=0, per_day=0, days=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "none deployed" in painted(app, "bid") and "DEPLOYED" not in painted(app, "bid")
        assert any("addresses" in line and "--" in line for line in painted(app, "vault").splitlines())
        assert "0 IMD" in painted(app, "queue") and "0 IMD/d" in painted(app, "queue") and "--d" in painted(app, "queue")
        app.query_one(SurfPool4RackHero).update_data(surf_pool4_hero=None)
        await pilot.pause()
        assert all("unavailable" in painted(app, key) for key in payload())
        assert "none deployed" not in painted(app, "bid")


async def test_zero_price_apr_and_holder_count_are_visible_before_unread():
    data = payload()
    data["price"]["usd"] = data["staking"]["apr"] = data["vault"]["holders"] = 0
    zero_rows = {"price": "╰─╯•╰─╯╰─╯╰─╯", "staking": "╰─╯•╰─╯"}
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for key, glyphs in zero_rows.items():
            assert glyphs in painted(app, key)
        assert any(line.strip("│ ").split() == ["addresses", "0"]
                   for line in painted(app, "vault").splitlines())
        app.query_one(SurfPool4RackHero).update_data(surf_pool4_hero=None)
        await pilot.pause()
        for key, glyphs in zero_rows.items():
            output = painted(app, key)
            assert "--" in output and "unavailable" in output and glyphs not in output
        assert any("addresses" in line and "--" in line
                   for line in painted(app, "vault").splitlines())


async def test_source_clocks_and_holder_provenance_remain_distinct(local_clock):
    data = payload()
    data["rate"].update(state="stale", read_ts=1791774000.)
    data["vault"].update(state="partial", read_ts=1791773400., holders=None,
                         holders_state="stale", holders_read_ts=1791773400.)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "stale 05:00" in painted(app, "rate")
        assert "partial 04:50" in painted(app, "vault")
        assert "82.4k" in painted(app, "vault")
        assert "holders stale" in str(app.query_one("#hero-vault").tooltip)
        assert "04:50 local" in str(app.query_one("#hero-vault").tooltip)
        card = app.query_one("#hero-vault")
        footer = app.screen._compositor.render_strips()[card.region.bottom-1].crop(card.region.x, card.region.right)
        assert any(segment.style.color.get_truecolor() == app.ansi_theme.ansi_colors[3]
                   for segment in footer if "partial" in segment.text)


@pytest.mark.parametrize("venue,gap,expected", [("reference", 1.2, "ref -1.20%"), (None, .1, "no venue edge"), (None, None, "venue --"), ("[/x]\x1b", .1, "no venue edge")])
async def test_price_venue_subtitle_does_not_invent_an_edge(venue, gap, expected):
    data = payload()
    data["price"].update(venue=venue, gap_pct=gap)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert expected in painted(pilot.app, "price")


@pytest.mark.parametrize("amount,expected", [(0.0000000042, "4.2e-09"), (0.001234, "0.001234"), (123456789012345., "1.235e+14")])
async def test_tiny_and_large_amounts_preserve_nonzero_faces_and_units(amount, expected):
    data = payload()
    for key, field in (("price", "usd"), ("rate", "imd"), ("staking", "apr"), ("bid", "eth")):
        data[key][field] = amount
    data["queue"].update(imd=amount, per_day=amount, days=amount)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for key in ("price", "rate", "staking", "bid"):
            assert expected in painted(app, key)
        assert "IMD/d" in painted(app, "queue")
        assert "0 IMD" not in painted(app, "queue")
        assert "┘" in painted(app, "queue")


async def test_partial_holder_fold_is_shown_as_a_lower_bound():
    data = payload()
    data["vault"].update(state="partial", holders=12, holders_state="partial")
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert any("addresses" in line and "≥12" in line for line in painted(pilot.app, "vault").splitlines())


async def test_clipped_cards_advertise_widen_and_clear_the_marker_on_resize():
    data = payload()
    data["queue"].update(imd=250000, per_day=12500)
    data["vault"]["holders"] = 999999
    async with Harness(data).run_test(size=(119, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for key in ("bid", "queue", "vault"):
            assert "‹" in painted(app, key), (key, painted(app, key))
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        for key in payload():
            assert "‹" not in painted(app, key), (key, painted(app, key))
        assert "DOWNSIDE BID" in painted(app, "bid")
        assert any("addresses" in line and "1000k" in line for line in painted(app, "vault").splitlines())
        assert any("cap" in line and "12.5k IMD/d" in line for line in painted(app, "queue").splitlines())
        await pilot.resize_terminal(119, 45)
        await pilot.pause()
        assert "‹" in painted(app, "bid")


async def test_stale_incomplete_holders_keep_their_lower_bound_and_date(local_clock):
    data=payload()
    data['vault'].update(state='stale',read_ts=1791773400.,holders_state='stale',
                         holders_read_ts=1791773400.,holders_partial=True)
    async with Harness(data).run_test(size=(149,45)) as pilot:
        await pilot.pause()
        text=painted(pilot.app,'vault')
        assert '≥126' in text and 'stale 04:50' in text
        assert 'holders stale' in str(pilot.app.query_one('#hero-vault').tooltip)


def test_parked_legacy_hero_signature_stays_frozen():
    import inspect
    from maxpane_dashboard.data.surf_models import POOL4_PARKED_WIDGET_SIGNATURES
    from maxpane_dashboard.widgets.surf import SurfPool4UserHero
    assert tuple(name for name,param in inspect.signature(SurfPool4UserHero.update_data).parameters.items()
                 if name != "self" and param.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)) == POOL4_PARKED_WIDGET_SIGNATURES['SurfPool4UserHero']
