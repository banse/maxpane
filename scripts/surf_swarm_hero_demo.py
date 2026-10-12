"""Standalone six-card SWARM hero mockup; all records are fictional.

Run: .venv/bin/python scripts/surf_swarm_hero_demo.py
Export: add --export /tmp/surf-swarm-heroes.svg --size 149x45
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Static

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_latest import SurfSwarmLatestLaunches
from maxpane_dashboard.widgets.surf.swarm_launches import SurfSwarmLaunches
from maxpane_dashboard.widgets.surf.swarm_sites import SurfSwarmSites
from maxpane_dashboard.widgets.surf.swarm_workflows import SurfSwarmWorkflows
from scripts.surf_start_demo import parse_size


MOCK_OBJECTIVE = "Build a shared workspace for agent reviews and deployment notes."
MOCK_CARDS = (
    HeroRecord("fleet", "FLEET", "STATS", "AGENTS",
               stats=(("online", "966"), ("working", "8"), ("enrolled", "1,972"))),
    HeroRecord("output", "OUTPUT", "24H", "24H",
               stats=(("steps", "2,621"), ("jobs", "224"), ("oracles", "48")),
               points=(148, 204, 322, 486, 391, 276, 338, 456)),
    HeroRecord("workflows", "WORKFLOWS", "STATUS", "JOBS", "149 cached",
               stats=(("completed", "142"), ("running", "4"), ("blocked", "3"))),
    HeroRecord("launches", "LAUNCHES", "STATUS", "DEPLOYMENTS", "49 cached",
               stats=(("live", "47"), ("parked", "2"))),
    HeroRecord("workflow", "LATEST WORKFLOW", "OBJECTIVE", "RUNNING", "8m ago", preview=MOCK_OBJECTIVE),
    HeroRecord("sites", "SITES", "CURRENT", "ENS", "named sites", digits="63"),
)

# Fixed demonstration snapshot and small body excerpts; no live clock or client.
MOCK_TIME = datetime(2026, 10, 12, 3, 30, tzinfo=timezone.utc).timestamp()
MOCK_WORKFLOWS = [
    dict(id="demo-review", status="running", created_ts=MOCK_TIME - 480, objective=MOCK_OBJECTIVE),
    dict(id="demo-launch", status="completed", created_ts=MOCK_TIME - 2400,
         objective="Publish the NOVA launch dashboard."),
    dict(id="demo-audit", status="completed", created_ts=MOCK_TIME - 5100,
         objective="Review the latest token deployment."),
    dict(id="demo-export", status="blocked", created_ts=MOCK_TIME - 7200,
         objective="Export a static site.", failure="Waiting for a static build artifact."),
    dict(id="demo-site", status="completed", created_ts=MOCK_TIME - 10800,
         objective="Add launch history to the project site."),
]
MOCK_LAUNCHES = [
    dict(launch_number=number, ticker=ticker, status="live", production=True,
         kind="erc20", chain_id=1, created_ts=MOCK_TIME - age,
         verdict=dict(state="swarm"), site_label=label, artifacts=[],
         parked_reason="")
    for number, ticker, age, label in (
        (49, "NOVA", 840, "demo-nova"), (48, "ORBIT", 3600, "demo-orbit"),
        (47, "SPARK", 7200, "demo-spark"), (46, "MESH", 10800, "demo-mesh"),
        (45, "WAVE", 14400, "demo-wave"),
    )
]
MOCK_SITES = [
    dict(label=label, ens_name=f"{label}.site.identitymd.eth", status="named", bytes=size)
    for label, size in (("demo-review", 184200), ("demo-nova", 98200), ("demo-orbit", 126400))
]


class SurfSwarmHeroDemo(App):
    """Approved balanced overview above the native SWARM tables."""

    TITLE = "SWARM / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #swarm-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #swarm-body { height: 1fr; min-height: 28; }
    #workflows-row { height: 1fr; min-height: 9; margin-bottom: 1; }
    #swarm-body SurfSwarmLaunches { height: 1fr; min-height: 9; margin-bottom: 1; }
    #swarm-body SurfSwarmSites { height: 8; min-height: 8; margin-bottom: 0; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("SWARM / SURFBOARD                                      MOCK DATA · HERO PROPOSAL 2"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="swarm-heroes")
                with Vertical(id="swarm-body"):
                    with Horizontal(id="workflows-row"):
                        yield SurfSwarmWorkflows()
                        yield SurfSwarmLatestLaunches()
                    yield SurfSwarmLaunches()
                    yield SurfSwarmSites()
        yield Static(Text("q quit · MOCK DATA · fictional figures and table excerpts · no API connection"), id="demo-footer")

    def on_mount(self):
        self.query_one(SurfSwarmWorkflows).update_data(swarm_workflow_rows=MOCK_WORKFLOWS)
        self.query_one(SurfSwarmLatestLaunches).update_data(swarm_launch_rows=MOCK_LAUNCHES, as_of=MOCK_TIME)
        self.query_one(SurfSwarmLaunches).update_data(swarm_launch_rows=MOCK_LAUNCHES)
        self.query_one(SurfSwarmSites).update_data(swarm_site_rows=MOCK_SITES)


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfSwarmHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="SWARM / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfSwarmHeroDemo().run()


if __name__ == "__main__":
    main()
