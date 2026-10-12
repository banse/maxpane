"""Leaderboard rack facts and independent source clocks, composited."""
import time
import pytest
from rich.color import Color
from textual.app import App
from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_board_hero import SurfSwarmBoardHero
from tests.surf_swarm_fixtures import swarm_capture_v3
from tests.widgets.surf_compositing import composite_lines


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
        top=dict(source, token_id=527, accepted=4180, rank=1, empty=False),
        recorded=dict(source, seats=1024, attempts=100000),
        rate=dict(source, accepted=96000, attempts=100000, percent=96.),
        outcomes=dict(source, rejected=2000, failed=1000, pending=1000),
        workers=dict(source, live=966, working=24, capacity=2880),
        effort=dict(source, receipts=18400, turns=580000, hours=18000.),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfSwarmBoardHero()
    def on_mount(self):
        self.query_one(SurfSwarmBoardHero).update_data(surf_leaderboard_hero=self.data)


def strips(app, key):
    region = app.query_one(f"#hero-{key}").region
    return [strip.crop(region.x, region.right)
            for strip in app.screen._compositor.render_strips()[region.y:region.bottom]]


def painted(app, key):
    return "\n".join(strip.text for strip in strips(app, key))


async def test_six_approved_cards_preserve_digits_counts_and_equal_geometry():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["TOP SEAT", "RECORDED", "ACCEPT RATE", "OUTCOMES", "WORKERS", "EFFORT"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for key, glyph, words in (
            ("top", "╶─╯╰─╴  ╵", ("SEAT", "4.18k accepted", "RANK 1")),
            ("recorded", "╶┴╴╰─╯╰─╴  ╵", ("SEATS", "100k attempts", "RECORDS")),
            ("rate", "╶─╯╰─╯•╰─╯", ("%", "96k / 100k", "ACCEPTED")),
        ):
            text = painted(app, key)
            assert glyph in text and all(word in text for word in words), text
        for key, pairs in {
            "outcomes": (("rejected", "2k"), ("failed", "1k"), ("pending", "1k")),
            "workers": (("live", "966"), ("working", "24"), ("capacity", "2,880")),
            "effort": (("receipts", "18.4k"), ("turns", "580k"), ("hours", "18k")),
        }.items():
            text = painted(app, key)
            lines = [next(line for line in text.splitlines() if label in line) for label, _ in pairs]
            assert all(value in line for (_, value), line in zip(pairs, lines))
            assert len({line.index(label) for (label, _), line in zip(pairs, lines)}) == 1
            assert len({line.index(value) + len(value) for (_, value), line in zip(pairs, lines)}) == 1
        green = Color.parse(app.get_css_variables()["accent"]).get_truecolor()
        background = Color.parse(app.get_css_variables()["background"]).get_truecolor()
        for key in payload():
            assert all(corner in painted(app, key) for corner in "┌┐└┘")
            frame = next(segment for strip in strips(app, key) for segment in strip if "┌" in segment.text)
            assert frame.style.color.get_truecolor() == green
            assert frame.style.bgcolor.get_truecolor() == background


async def test_exact_ten_digit_seat_id_is_never_compacted_or_rounded():
    data = payload()
    data["top"]["token_id"] = 9876543210
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        text = painted(pilot.app, "top")
        assert "9876543210" in text and "9.877" not in text


async def test_empty_records_and_no_attempts_are_real_negatives():
    data = payload()
    data["top"].update(token_id=None, accepted=None, rank=None, empty=True)
    data["recorded"].update(seats=0, attempts=0)
    data["rate"].update(accepted=0, attempts=0, percent=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "no recorded seats" in painted(pilot.app, "top")
        assert "no attempts" in painted(pilot.app, "rate")
        assert "0 attempts" in painted(pilot.app, "recorded")
        assert "╰─╯" in painted(pilot.app, "recorded")
        assert "unavailable" not in painted(pilot.app, "top")


async def test_known_zero_rate_and_counts_are_distinct_from_cold_and_recover():
    data = payload()
    data["top"].update(token_id=0, accepted=0)
    data["rate"].update(accepted=0, attempts=10, percent=0)
    data["workers"].update(live=0, working=0, capacity=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "╰─╯•╰─╯" in painted(app, "rate") and "0 / 10" in painted(app, "rate")
        assert "0 accepted" in painted(app, "top") and "╰─╯" in painted(app, "top")
        assert any("capacity" in line and "0" in line for line in painted(app, "workers").splitlines())
        app.query_one(SurfSwarmBoardHero).update_data(surf_leaderboard_hero=None)
        await pilot.pause()
        assert all("unavailable" in painted(app, key) for key in payload())
        assert "╰─╯•╰─╯" not in painted(app, "rate") and "0 accepted" not in painted(app, "top")
        app.query_one(SurfSwarmBoardHero).update_data(surf_leaderboard_hero=payload())
        await pilot.pause()
        assert "4.18k accepted" in painted(app, "top") and "96k / 100k" in painted(app, "rate")


async def test_partial_stale_and_failed_sources_remain_independent(local_clock):
    data = payload()
    for key in ("top", "recorded", "rate", "outcomes"):
        data[key].update(state="stale", read_ts=1791773400.)
    data["effort"].update(state="partial", read_ts=1791774000., turns=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "4.18k accepted" in painted(app, "top") and "stale 04:50" in painted(app, "top")
        assert "partial 05:00" in painted(app, "effort") and "18.4k" in painted(app, "effort")
        assert any("turns" in line and "--" in line for line in painted(app, "effort").splitlines())
        assert "CURRENT" in painted(app, "workers") and "966" in painted(app, "workers")
        data["workers"]["state"] = "unavailable"
        app.query_one(SurfSwarmBoardHero).update_data(surf_leaderboard_hero=data)
        await pilot.pause()
        assert "966" not in painted(app, "workers") and "unavailable" in painted(app, "workers")
        assert "18.4k" in painted(app, "effort")


@pytest.mark.parametrize("bad", [True, -1, 1.5, float("nan"), float("inf"), "[/x]", {}])
async def test_malformed_identifiers_counts_and_clocks_cannot_paint_old_values(bad):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        data = payload()
        data["top"].update(state="stale", read_ts="[/x]PWNED", token_id=bad, accepted=bad, rank=bad)
        data["outcomes"]["rejected"] = bad
        pilot.app.query_one(SurfSwarmBoardHero).update_data(surf_leaderboard_hero=data)
        await pilot.pause()
        text = painted(pilot.app, "top")
        assert "4.18k" not in text and "-- accepted" in text and "stale --:--" in text
        assert "[/x]" not in text and "PWNED" not in text
        assert any("rejected" in line and "--" in line for line in painted(pilot.app, "outcomes").splitlines())


@pytest.mark.parametrize("percent", [-1, 101, True, float("nan"), "[/x]"])
async def test_invalid_percent_is_unknown_instead_of_a_success_rate(percent):
    data = payload()
    data["rate"]["percent"] = percent
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "--" in painted(pilot.app, "rate")
        assert "╶─╯╰─╯•╰─╯" not in painted(pilot.app, "rate")


async def test_small_effort_hours_and_tiny_nonzero_accept_rate_remain_visible():
    data = payload()
    data["effort"]["hours"] = .0000000042
    data["rate"].update(accepted=1, attempts=100000000, percent=.000001)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "4.2e-09" in painted(pilot.app, "effort")
        assert "1e-06" in painted(pilot.app, "rate")
        assert "╰─╯•╰─╯" not in painted(pilot.app, "rate")


async def test_large_counts_and_narrow_cards_mark_then_recover_on_resize():
    data = payload()
    data["effort"]["receipts"] = 123456789012345
    async with Harness(data).run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        assert "‹" in painted(pilot.app, "top") and "‹" in painted(pilot.app, "effort")
        await pilot.resize_terminal(170, 45)
        await pilot.pause()
        assert "1.235e+14" in painted(pilot.app, "effort")
        assert "4.18k accepted" in painted(pilot.app, "top")
        assert all("‹" not in painted(pilot.app, key) for key in payload())


# Native widgets still consume the original, independent source-clock contract.
SUMMARY = fold.board_summary(swarm_capture_v3("contributors"), swarm_capture_v3("workers"))
SUMMARY.update(seats=50, attempts=100, accepted=80, rejected=5, failed=3, pending=12)


@pytest.mark.parametrize("widget_name", ["SurfSwarmLeaderboard", "SurfSwarmFleet"])
async def test_invalid_source_clocks_are_explicit_and_never_painted(widget_name):
    import maxpane_dashboard.widgets.surf as widgets
    text = "\n".join(await composite_lines(getattr(widgets, widget_name), (150, 20), css_path=CSS_PATH,
        swarm_board_summary=SUMMARY,
        swarm_board_rows=fold.board_rows(swarm_capture_v3("contributors"), swarm_capture_v3("workers")),
        swarm_fleet=fold.fleet(swarm_capture_v3("workers")),
        swarm_board_as_of_hhmm="[/x]PWNED", swarm_workers_as_of_hhmm="99:99"))
    assert "unavailable" in text
    assert "PWNED" not in text and "99:99" not in text and "[/x]" not in text
