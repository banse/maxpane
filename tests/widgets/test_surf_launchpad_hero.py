"""Launchpad rack facts, source provenance and precision in the compositor."""
import time

import pytest
from rich.color import Color
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.launchpad_hero import SurfLaunchpadHero
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard


@pytest.fixture(autouse=True)
def offline_colors(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("widget tests must not use the network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


@pytest.fixture
def local_clock(monkeypatch):
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv("TZ", "Europe/Berlin")
            time.tzset()
            yield
    finally:
        time.tzset()


def payload():
    source = dict(state="ok", read_ts=1791775800.)
    return dict(
        coins=dict(source, count=210, new_24h=2, swept=210),
        flow=dict(source, swaps=12400, traders=486, creators=64),
        volume=dict(source, usd=42600., points=(2800, 4100, 2500, 6200, 9800, 5600, 4300, 7300),
                    until=1791774000., known=210, total=210, quote=3200.,
                    quote_read_ts=1791775800., volume_read_ts=1791775200.),
        fees=dict(source, eth=.0842),
        queue=dict(source, accrued=250., staged=120., sendable=120., ready=True),
        burned=dict(source, imd=15700.),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield SurfLaunchpadHero()

    def on_mount(self):
        self.query_one(SurfLaunchpadHero).update_data(surf_launchpad_hero=self.data)


def strips(app, key):
    region = app.query_one(f"#hero-{key}").region
    return [strip.crop(region.x, region.right)
            for strip in app.screen._compositor.render_strips()[region.y:region.bottom]]


def painted(app, key):
    return "\n".join(strip.text for strip in strips(app, key))


def frame_color(app, key):
    frame = next(segment for strip in strips(app, key) for segment in strip if "┌" in segment.text)
    return frame.style.color.get_truecolor()


async def test_six_approved_cards_keep_exact_fee_glyphs_and_lime_volume(local_clock):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["COINS", "CURVE FLOW", "VOLUME", "CREATOR FEES", "BURN QUEUE", "BURNED"]
        assert {card.region.height for card in cards} == {9}
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for key, glyph, words in (
            ("coins", "╰─╴╶┴╴╰─╯", ("COINS", "2 new /24h", "FACTORY")),
            ("volume", "  ╵╰─╴•╰─╯", ("kUSD", "2h to 05:00", "2H")),
            ("fees", "╰─╯•╰─╯╰─╯  ╵╰─╴", ("ETH", "owed", "UNCLAIMED")),
            ("burned", "╶┴╴╶─╯•  ╵", ("kIMD", "cumulative", "EVENT TOTAL")),
        ):
            text = painted(app, key)
            assert glyph in text and all(word in text for word in words), text
        for key, pairs in {
            "flow": (("swaps", "12.4k"), ("traders", "486"), ("creators", "64")),
            "queue": (("accrued", "250"), ("staged", "120"), ("sendable", "120")),
        }.items():
            lines = [next(line for line in painted(app, key).splitlines() if label in line) for label, _ in pairs]
            assert all(value in line for (_, value), line in zip(pairs, lines))
            assert len({line.index(label) for (label, _), line in zip(pairs, lines)}) == 1
            assert len({line.index(value) + len(value) for (_, value), line in zip(pairs, lines)}) == 1
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        for key in payload():
            assert frame_color(app, key) == green
            assert "‹" not in painted(app, key)
        spark = [segment for strip in strips(app, "volume") for segment in strip if any(c in segment.text for c in "▁▂▃▄▅▆▇█")]
        assert spark and all(segment.style.color.get_truecolor(app.ansi_theme) == app.ansi_theme.ansi_colors[2] for segment in spark)


async def test_volume_tooltip_has_independent_clocks_and_conversion_basis(local_clock):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        tip = str(pilot.app.query_one("#hero-volume").tooltip)
        assert all(word in tip for word in ("05:30", "05:20", "05:00", "local", "3.2k", "ETH/USD", "current", "210/210", "8 completed 15m")), tip


async def test_partial_history_retains_factory_count_and_independent_current_getters(local_clock):
    data = payload()
    data["coins"].update(state="partial", read_ts=1791773400., swept=150)
    data["flow"].update(state="partial", read_ts=1791773400., traders=None)
    data["burned"].update(state="partial", read_ts=1791773400.)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "╰─╴╶┴╴╰─╯" in painted(app, "coins") and "2 new /24h" in painted(app, "coins")
        assert "150/210" in str(app.query_one("#hero-coins").tooltip)
        for key in ("coins", "flow", "burned"):
            assert "partial 04:50" in painted(app, key)
            assert frame_color(app, key) != Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        assert any("traders" in line and "0" in line for line in painted(app, "flow").splitlines())
        assert "12.4k" in painted(app, "flow") and "UNCLAIMED" in painted(app, "fees") and "READY" in painted(app, "queue")


@pytest.mark.parametrize("ready,label", [(True, "READY"), (False, "WAITING"), (None, "UNKNOWN"), ("[/x]READY", "UNKNOWN")])
async def test_queue_readiness_survives_degraded_footer(ready, label, local_clock):
    data = payload()
    data["queue"].update(state="stale", read_ts=1791774000., ready=ready)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, "queue")
        assert label in text and "stale" not in text and "05:00" in str(pilot.app.query_one("#hero-queue").tooltip) and "250" in text
        assert "[/x]" not in text


async def test_genuine_zeros_have_a_chart_and_waiting_is_not_an_outage():
    data = payload()
    data["coins"].update(count=0, swept=0, new_24h=0)
    data["flow"].update(swaps=0, traders=0, creators=0)
    data["volume"].update(usd=0., points=(0.,) * 8, known=0, total=0)
    data["fees"]["eth"] = 0.
    data["queue"].update(accrued=0., staged=0., sendable=0., ready=False)
    data["burned"]["imd"] = 0.
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "0 new /24h" in painted(app, "coins")
        assert "╰─╯•╰─╯" in painted(app, "volume") and "▁" in painted(app, "volume")
        assert "╰─╯" in painted(app, "fees") and "--" not in painted(app, "fees")
        assert "WAITING" in painted(app, "queue")
        assert any("creators" in line and "0" in line for line in painted(app, "flow").splitlines())
        assert all("unavailable" not in painted(app, key) for key in data)


async def test_unread_and_partial_volume_do_not_keep_a_chart_and_full_refresh_recovers(local_clock):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        data = payload()
        data["volume"].update(state="partial", read_ts=1791773400., usd=None, points=None, known=50)
        app.query_one(SurfLaunchpadHero).update_data(surf_launchpad_hero=data)
        await pilot.pause()
        text = painted(app, "volume")
        assert "partial 04:50" in text and "  ╵╰─╴•╰─╯" in text
        assert not any(c in text for c in "▁▂▃▄▅▆▇█")
        assert "50/210" in str(app.query_one("#hero-volume").tooltip)
        app.query_one(SurfLaunchpadHero).update_data(surf_launchpad_hero=None)
        await pilot.pause()
        for key in data:
            assert "unavailable" not in painted(app, key)
        assert "12.4k" in painted(app, "flow") and "READY" not in painted(app, "queue")
        assert "3.2k" not in str(app.query_one("#hero-volume").tooltip)
        app.query_one(SurfLaunchpadHero).update_data(surf_launchpad_hero=payload())
        await pilot.pause()
        assert "12.4k" in painted(app, "flow") and "READY" in painted(app, "queue")
        assert any(c in painted(app, "volume") for c in "▁▂▃▄▅▆▇█")


async def test_small_nonzero_amounts_are_never_rounded_to_zero():
    data = payload()
    data["fees"]["eth"] = 4.2e-9
    data["burned"]["imd"] = 4.2e-9
    data["queue"].update(accrued=.0042, staged=4.2e-9, sendable=4.2e-9)
    data["volume"].update(usd=4.2e-9, points=(5.25e-10,) * 8)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        for key in ("fees", "burned", "volume", "queue"):
            text = painted(pilot.app, key)
            assert "4.2e-09" in text, text
        assert "kUSD" not in painted(pilot.app, "volume") and "USD" in painted(pilot.app, "volume")
        assert "kIMD" not in painted(pilot.app, "burned") and "IMD" in painted(pilot.app, "burned")


async def test_volume_retains_its_last_value_while_source_metadata_changes(local_clock):
    data = payload()
    data["volume"].update(state="stale", read_ts=1791773400.)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "  ╵╰─╴•╰─╯" in painted(app, "volume")
        assert "stale" not in painted(app, "volume") and "04:50" in str(app.query_one("#hero-volume").tooltip) and "2h to 05:00" in painted(app, "volume")
        assert "05:30" in str(app.query_one("#hero-volume").tooltip)
        for section in data.values():
            section["state"] = "unavailable"
        app.query_one(SurfLaunchpadHero).update_data(surf_launchpad_hero=data)
        await pilot.pause()
        for key in data:
            assert "unavailable" not in painted(app, key)
        assert "  ╵╰─╴•╰─╯" in painted(app, "volume") and "2h to 05:00" in painted(app, "volume")
        assert "12.4k" in painted(app, "flow") and "250" in painted(app, "queue")


async def test_failed_usd_read_keeps_covered_volume_metadata_in_tooltip(local_clock):
    data = payload()
    data["volume"].update(state="unavailable", usd=None, points=None, quote=None, quote_read_ts=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "unavailable" not in painted(app, "volume")
        assert "  ╵╰─╴•╰─╯" not in painted(app, "volume")
        tip = str(app.query_one("#hero-volume").tooltip)
        assert all(word in tip for word in ("210/210", "until 05:00 local", "volume read 05:20 local", "ETH/USD --", "quote read --:-- local")), tip


async def test_fractional_counts_and_one_invalid_bucket_are_not_valid_data():
    data = payload()
    data["coins"].update(count=1.5, new_24h=1.5)
    data["flow"].update(swaps=1.5)
    data["volume"]["points"] = (1., 2., 3., 4., None, 6., 7., 8.)
    data["queue"]["ready"] = None
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "0 new /24h" in painted(app, "coins")
        assert any("swaps" in row and "0" in row for row in painted(app, "flow").splitlines())
        assert not any(c in painted(app, "volume") for c in "▁▂▃▄▅▆▇█")
        assert "UNKNOWN" in painted(app, "queue") and "120" in painted(app, "queue")
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        assert all(frame_color(app, key) != green for key in ("coins", "flow", "volume", "queue"))


@pytest.mark.parametrize("bad", [True, -1, float("nan"), float("inf"), "[/x]PWNED", {}])
async def test_invalid_values_and_dates_are_safe_unknowns(bad):
    data = payload()
    data["coins"].update(count=bad, new_24h=bad)
    data["fees"].update(state="stale", read_ts=bad, eth=bad)
    data["volume"].update(usd=bad, until=bad, points=[bad] * 8, quote=bad, quote_read_ts=bad)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "0 new /24h" in painted(app, "coins")
        assert "stale" not in painted(app, "fees") and "--:--" in str(app.query_one("#hero-fees").tooltip)
        assert "2h to" not in painted(app, "volume")
        assert app.query_one("#hero-volume").source_record.subtitle == "2h to --:--"
        assert "--" not in painted(app, "fees")
        assert app.query_one("#hero-fees").data.digits == ""
        assert all("PWNED" not in painted(app, key) for key in data)
        assert "PWNED" not in str(app.query_one("#hero-volume").tooltip)
        assert frame_color(app, "coins") != Color.parse(app.get_css_variables()["accent"]).get_truecolor()


async def test_large_values_and_narrow_markers_recover_after_resize():
    data = payload()
    data["flow"]["creators"] = 123456789012345
    data["coins"]["count"] = 123456789012345
    data["fees"]["eth"] = 123456789012345.
    async with Harness(data).run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        assert "‹" in painted(pilot.app, "flow") and "‹" in painted(pilot.app, "fees")
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        for key in ("coins", "flow", "fees"):
            assert "1.235e+14" in painted(pilot.app, key)
            assert "‹" not in painted(pilot.app, key)


async def test_exact_counts_and_short_queue_label_keep_all_large_values():
    data = payload()
    data["flow"]["creators"] = 9999
    data["queue"].update(accrued=123456.7, staged=123456.7, sendable=123456.7)
    async with Harness(data).run_test(size=(141, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert any("creators" in row and "9,999" in row for row in painted(app, "flow").splitlines())
        assert any("ready" in row and "123.5k" in row for row in painted(app, "queue").splitlines())
        assert "‹" not in painted(app, "flow") and "‹" not in painted(app, "queue")
        assert "sendable 123.5k" in str(app.query_one("#hero-queue").tooltip)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert any("sendable" in row and "123.5k" in row for row in painted(app, "queue").splitlines())
