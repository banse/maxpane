"""Live SWARM projection painted with the approved rack hero design."""
import pytest
from textual.app import App

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_rack_hero import SurfSwarmRackHero


@pytest.fixture(autouse=True)
def offline_color_environment(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def refuse(*args, **kwargs):
        raise AssertionError("widget tests must never request the network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


def payload():
    source = dict(state="ok", read_ts=1791775800.0)
    return dict(
        fleet=dict(source, online=966, working=8, enrolled=1972),
        output=dict(source, steps=2621, jobs=224, oracles=48, points=[148, 204, 322, 486],
                    points_state="ok", points_read_ts=1791775800.0),
        workflows=dict(source, total=149, statuses=[dict(status="completed", count=142),
                       dict(status="reviewing", count=4), dict(status="queued", count=3)]),
        launches=dict(source, total=49, statuses=[dict(status="live", count=47), dict(status="parked", count=2)]),
        workflow=dict(source, objective="Build a shared workspace for agent reviews and deployment notes.", age_s=480, status="reviewing"),
        sites=dict(source, count=63),
    )


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; }"

    def __init__(self, data=None):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self):
        yield SurfSwarmRackHero()

    def on_mount(self):
        self.query_one(SurfSwarmRackHero).update_data(surf_swarm_hero=self.data)


def painted(app, key):
    card = app.query_one(f"#hero-{key}")
    region = card.region
    return "\n".join(strip.crop(region.x, region.right).text
                     for strip in app.screen._compositor.render_strips()[region.y:region.bottom])


async def test_live_projection_preserves_the_selected_six_card_layout():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "FLEET", "OUTPUT", "WORKFLOWS", "LAUNCHES", "LATEST WORKFLOW", "SITES"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert all(left.region.right < right.region.x for left, right in zip(cards, cards[1:]))
        for key, values in {
            "fleet": ("online", "966", "working", "8", "enrolled", "1,972"),
            "output": ("steps", "2,621", "jobs", "224", "oracles", "48", "24H", "█"),
            "workflows": ("completed", "142", "reviewing", "4", "queued", "3", "149 cached"),
            "launches": ("live", "47", "parked", "2", "49 cached"),
            "workflow": ("OBJECTIVE", "Build a shared", "8m ago", "REVIEWING", "..."),
            "sites": ("CURRENT", "named sites", "ENS", "╭─╴╶─╮"),
        }.items():
            output = painted(app, key)
            assert all(value in output for value in values), output
            assert all(corner in output for corner in "┌┐└┘")
        assert "running" not in painted(app, "workflows")


async def test_empty_zero_and_unavailable_keep_different_meanings():
    data = payload()
    data["fleet"].update(online=0, working=0, enrolled=None)
    data["output"].update(steps=0, jobs=0, oracles=None, points=[], points_state="unavailable")
    data["workflows"].update(total=0, statuses=[])
    data["launches"].update(state="unavailable", read_ts=None, total=None, statuses=None)
    data["workflow"].update(objective=None, age_s=None, status=None)
    data["sites"].update(count=0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert any("online" in line and "0" in line for line in painted(app, "fleet").splitlines())
        assert any("enrolled" in line and "--" in line for line in painted(app, "fleet").splitlines())
        assert "0 cached" in painted(app, "workflows") and "No workflows" in painted(app, "workflows")
        assert "—" in painted(app, "launches") and "0 cached" in painted(app, "launches")
        assert data["launches"]["total"] is None
        assert "No workflows in" in painted(app, "workflow") and "cache" in painted(app, "workflow")
        assert "24H" in painted(app, "output")
        app.query_one(SurfSwarmRackHero).update_data(surf_swarm_hero=None)
        await pilot.pause()
        assert all("unavailable" not in painted(app, key) for key in payload())
        assert all("0 cached" in painted(app, key) for key in ("workflows", "launches"))


@pytest.mark.parametrize("state,label", [("stale", "24H"), ("unavailable", "24H")])
async def test_output_chart_failure_does_not_degrade_current_overview(state, label):
    data = payload()
    data["output"].update(points_state=state, points_read_ts=1791774000.0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "output")
        assert "2,621" in output and "224" in output
        assert label in output and ("█" in output) == (state == "stale")
        assert "as of" in str(pilot.app.query_one("#hero-output").tooltip)


async def test_cached_records_keep_values_with_their_own_stale_clock():
    data = payload()
    data["workflows"].update(state="stale", read_ts=1791774000.0)
    data["sites"].update(state="stale", read_ts=1791774600.0)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "stale" not in painted(pilot.app, "workflows")
        assert "149 cached" in painted(pilot.app, "workflows")
        assert "stale" not in painted(pilot.app, "sites")


async def test_hostile_statuses_and_objectives_stay_literal_and_fitted():
    data = payload()
    data["workflows"]["statuses"] = [dict(status="[/x]\x1b中" * 4, count=123456789012345), dict(status="done", count=2)]
    data["workflow"]["objective"] = "[/x] 0x1234567890123456789012345678901234567890 " + "中" * 50
    data["workflow"]["status"] = "reviewing\x1b"
    data["sites"]["count"] = 123456789012345
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "1.23e+14" in painted(app, "workflows") and "…" in painted(app, "workflows")
        assert "1.23e+14" in painted(app, "sites")
        assert "[/x]" in painted(app, "workflow") and "⧉" in painted(app, "workflow")
        assert "..." in painted(app, "workflow")
        assert "REVIEWING" in painted(app, "workflow")
        region = app.query_one("#hero-workflow").region
        assert any(segment.style and "copy_address" in str(segment.style.meta)
                   for strip in app.screen._compositor.render_strips()[region.y:region.bottom]
                   for segment in strip.crop(region.x, region.right))


async def test_status_cards_keep_only_top_three_actual_labels():
    data = payload()
    data["workflows"]["statuses"].append(dict(status="retrying", count=1))
    data["workflows"]["total"] = 150
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "workflows")
        assert "reviewing" in output and "queued" in output and "150 cached" in output
        assert "retrying" not in output and "running" not in output


async def test_missing_objective_is_not_mistaken_for_an_empty_workflow_cache():
    data = payload()
    data["workflow"]["objective"] = None
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "workflow")
        assert "—" in output and "unavailable" not in output and "8m ago" in output
        assert "No workflows" not in output


@pytest.mark.parametrize("points", [None, [], [1]])
async def test_missing_or_short_history_never_draws_an_invented_chart(points):
    data = payload()
    data["output"]["points"] = points
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "output")
        assert "24H" in output and "2,621" in output
        assert not any(block in output for block in "▁▂▃▄▅▆▇█")


@pytest.mark.parametrize("key", ["workflows", "launches"])
async def test_nonempty_cache_without_statuses_is_not_an_empty_cache(key):
    data = payload()
    data[key].update(total=3, statuses=[])
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, key)
        assert "—" in output and "unavailable" not in output
        assert "3 cached" in output and f"No {key}" not in output
