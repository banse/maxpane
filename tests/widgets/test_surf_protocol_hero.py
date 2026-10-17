"""Protocol rack projections asserted against the composited terminal."""
import time

import pytest
from rich.color import Color
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.protocol_hero import SurfProtocolHero


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
        totals=dict(source, burned=33300., rewarded=5900., fees=3800.),
        inventory=dict(source, cap=840000., reserve=835000., headroom=5000.),
        split=dict(source, path="via-distributor", staking_pct=30., nodes_pct=30., bonding_pct=40.),
        unsettled=dict(source, burn=120., rewards=21.),
        delivery=dict(source, queued=7440., ready=250., per_day=1200.),
        checks=dict(source, counters="reconciled", drift_bps=0., path="via-distributor"),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield SurfProtocolHero()

    def on_mount(self):
        self.query_one(SurfProtocolHero).update_data(surf_protocol_hero=self.data)


def strips(app, key):
    region = app.query_one(f"#hero-{key}").region
    return [strip.crop(region.x, region.right)
            for strip in app.screen._compositor.render_strips()[region.y:region.bottom]]


def painted(app, key):
    return "\n".join(strip.text for strip in strips(app, key))


async def test_six_approved_cards_have_equal_geometry_and_visible_values():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["TOTALS", "INVENTORY", "REWARD SPLIT", "UNSETTLED", "DELIVERY", "CHECKS"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        rows = {
            "totals": (("burned", "33.3k"), ("rewarded", "5.9k"), ("fees", "3.8k")),
            "inventory": (("cap", "840k"), ("reserve", "835k"), ("headroom", "5k")),
            "split": (("staking", "30%"), ("nodes", "30%"), ("bonding*", "40%")),
            "unsettled": (("burn", "120"), ("rewards", "21")),
            "delivery": (("queued", "7.44k"), ("ready", "250"), ("cap", "1.2k/d")),
        }
        for key, pairs in rows.items():
            output = painted(app, key)
            assert all(corner in output for corner in "┌┐└┘")
            lines = [next(line for line in output.splitlines() if label in line) for label, _ in pairs]
            assert all(value in line for (_, value), line in zip(pairs, lines))
            assert len({line.index(label) for (label, _), line in zip(pairs, lines)}) == 1
            assert len({line.index(value) + len(value) for (_, value), line in zip(pairs, lines)}) == 1
        assert "* DERIVED" in painted(app, "split")
        assert all(word in painted(app, "checks") for word in ("reconciled", "drift 0.0 bps", "distributor", "ACCOUNTING"))
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        background = Color.parse(app.get_css_variables()["background"]).get_truecolor()
        for key in payload():
            frames = [segment for strip in strips(app, key) for segment in strip if "┌" in segment.text]
            assert frames and all(segment.style.color.get_truecolor() == green for segment in frames)
            assert all(segment.style.bgcolor.get_truecolor() == background for segment in frames)


async def test_zero_unknown_and_negative_headroom_survive_refresh_then_clear():
    data = payload()
    data["totals"].update(state="partial", burned=0, rewarded=None, fees=0)
    data["inventory"]["headroom"] = -5000
    data["delivery"].update(queued=0, ready=0, per_day=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert any("burned" in row and "0" in row for row in painted(app, "totals").splitlines())
        assert any("rewarded" in row and "--" in row for row in painted(app, "totals").splitlines())
        assert "-5k" in painted(app, "inventory")
        assert "0/d" in painted(app, "delivery")
        app.query_one(SurfProtocolHero).update_data(surf_protocol_hero=None)
        await pilot.pause()
        for key in payload():
            assert "unavailable" not in painted(app, key)
        assert "-5k" not in painted(app, "inventory")
        assert "reconciled" not in painted(app, "checks")
        assert "0/d" not in painted(app, "delivery")


async def test_partial_stale_source_times_and_derived_marker(local_clock):
    data = payload()
    data["totals"].update(state="stale", read_ts=1791774000.)
    data["split"].update(state="partial", read_ts=1791773400., nodes_pct=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "stale" not in painted(pilot.app, "totals") and "05:00" in str(pilot.app.query_one("#hero-totals").tooltip)
        assert "33.3k" in painted(pilot.app, "totals")
        assert "partial 04:50" in painted(pilot.app, "split")
        assert "* derived" in painted(pilot.app, "split")
        assert "bonding*" in painted(pilot.app, "split")


@pytest.mark.parametrize("counters,drift", [("mismatch", 0), ("reconciled", 1.2), ("reconciled", -0.000002)])
async def test_accounting_faults_are_visible_red_and_never_healthy(counters, drift):
    data = payload()
    data["checks"].update(counters=counters, drift_bps=drift)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        output = painted(app, "checks")
        assert "CHECK FAILED" in output
        if counters == "mismatch":
            assert "MISMATCH" in output
        if drift != 0:
            assert "drift 0.0 bps" not in output
        red = app.ansi_theme.ansi_colors[1]
        frames = [segment for strip in strips(app, "checks") for segment in strip if "┌" in segment.text]
        assert frames and all(segment.style.color.get_truecolor() == red for segment in frames)
        card = app.query_one("#hero-checks")
        lines = output.splitlines()
        index = next(i for i, row in enumerate(lines) if "drift " in row)
        row = lines[index]
        amount_start, amount_end = row.index("drift ") + len("drift "), row.index(" bps")
        for x in range(amount_start, amount_end):
            assert app.screen.get_style_at(card.region.x + x, card.region.y + index).color == Color.parse(app.get_css_variables()["foreground"])
        for text in ("drift", "bps"):
            assert app.screen.get_style_at(card.region.x + row.index(text), card.region.y + index).color == card.rich_style.color


@pytest.mark.parametrize("counters", ["window-limited", "unchecked", None])
async def test_unestablished_counters_are_neutral(counters):
    data = payload()
    data["checks"]["counters"] = counters
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "not established" in painted(app, "checks")
        if counters:
            assert counters in painted(app, "checks")
        assert "CHECK FAILED" not in painted(app, "checks")
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        frames = [segment for strip in strips(app, "checks") for segment in strip if "┌" in segment.text]
        assert frames and all(segment.style.color.get_truecolor() != green for segment in frames)


async def test_stale_fault_retains_alarm_and_a_fresh_recovery_clears_it(local_clock):
    data = payload()
    data["checks"].update(state="stale", counters="mismatch", read_ts=1791773400.)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "MISMATCH" in painted(app, "checks") and "stale" not in painted(app, "checks") and "04:50" in str(app.query_one("#hero-checks").tooltip)
        red = app.ansi_theme.ansi_colors[1]
        assert any(segment.style.color.get_truecolor() == red
                   for strip in strips(app, "checks") for segment in strip if "┌" in segment.text)
        assert any(segment.style.color == app.query_one('#hero-checks').rich_style.color
                   for strip in strips(app, "checks") for segment in strip if "MISMATCH" in segment.text)
        app.query_one(SurfProtocolHero).update_data(surf_protocol_hero=payload())
        await pilot.pause()
        assert "MISMATCH" not in painted(app, "checks") and "stale" not in painted(app, "checks")
        assert "reconciled" in painted(app, "checks")
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        assert any(segment.style.color.get_truecolor() == green
                   for strip in strips(app, "checks") for segment in strip if "┌" in segment.text)


@pytest.mark.parametrize("route,expected", [("direct", "to stakers"), ("[/x]\x1b", "route --"), (None, "route --")])
async def test_routes_never_invent_distributor_allocations(route, expected):
    data = payload()
    data["split"]["path"] = data["checks"]["path"] = route
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "split")
        assert expected in output
        assert "30%" not in output and "40%" not in output
        assert "distributor" not in painted(pilot.app, "checks")
        assert "[/x]" not in output


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), "[/x]\x1b", {}, -(10 ** 500)])
async def test_invalid_values_and_dates_do_not_leave_old_data_or_raise(bad):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        data = payload()
        data["totals"].update(state="stale", read_ts=bad, burned=bad)
        data["checks"].update(counters=bad, drift_bps=bad, path=bad)
        pilot.app.query_one(SurfProtocolHero).update_data(surf_protocol_hero=data)
        await pilot.pause()
        text = painted(pilot.app, "totals")
        assert "33.3k" not in text and "stale" not in text and "--:--" in str(pilot.app.query_one("#hero-totals").tooltip)
        assert any("burned" in row and "--" in row for row in text.splitlines())
        assert "reconciled" not in painted(pilot.app, "checks")


@pytest.mark.parametrize("amount,expected", [(0.0000000042, "4.2e-09"), (0.001234, "0.001234"), (123456789012345., "1.235e+14")])
async def test_magnitude_and_signed_headroom_keep_nonzero_values(amount, expected):
    data = payload()
    data["inventory"]["headroom"] = -amount
    data["delivery"]["queued"] = amount
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "-" + expected in painted(pilot.app, "inventory")
        assert expected in painted(pilot.app, "delivery")


async def test_clipping_marks_and_recovers_at_the_owner_width():
    async with Harness(payload()).run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        assert "‹" in painted(pilot.app, "split")
        assert "‹" in painted(pilot.app, "inventory")
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert all("‹" not in painted(pilot.app, key) for key in payload())


async def test_short_labels_keep_full_signed_values_and_restore_on_resize():
    data = payload()
    data["totals"]["rewarded"] = 1_234_567.89
    data["inventory"]["headroom"] = -1_234_567.89
    async with Harness(data).run_test(size=(141, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert any("rewards" in row and "1.235M" in row for row in painted(app, "totals").splitlines())
        assert any("room" in row and "-1.235M" in row for row in painted(app, "inventory").splitlines())
        assert "‹" not in painted(app, "totals") and "‹" not in painted(app, "inventory")
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert any("rewarded" in row and "1.235M" in row for row in painted(app, "totals").splitlines())
        assert any("headroom" in row and "-1.235M" in row for row in painted(app, "inventory").splitlines())
