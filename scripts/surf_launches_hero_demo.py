"""Standalone LAUNCHES hero mockup; every market value is fictional.

Run: .venv/bin/python scripts/surf_launches_hero_demo.py
Export: add --export /tmp/surf-launches-heroes.svg --size 149x45
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
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.swarm_tokens import BestPlays, NewlyLaunched, TokenActivity, TokensTable
from scripts.surf_start_demo import parse_size


MOCK_CARDS = (
    HeroRecord("tokens", "TOKENS", "STATS", "SELECTION",
               stats=(("tracked", "48"), ("new 24h", "4"), ("chains", "3"))),
    HeroRecord("volume", "VOLUME", "kUSD / 24H", "MEASURED", "41/48 known", digits="124.8"),
    HeroRecord("liquidity", "LIQUIDITY", "PAIRED", "QUOTE ASSETS", "43/48 known",
               rows=("≥12.4k IMD", "≥3.8 ETH")),
    HeroRecord("pools", "POOLS", "STATE", "LIQUIDITY",
               stats=(("two-sided", "35"), ("one-sided", "8"), ("unknown", "5"))),
    HeroRecord("momentum", "MOMENTUM", "24H", "PRICE CHANGE", "41/48 known",
               stats=(("rising", "22"), ("falling", "14"), ("flat", "5"))),
    HeroRecord("top-volume", "TOP VOLUME", "USD / 24H", "LEADERS",
               stats=(("ORBIT", "$38.2k"), ("BMC", "$21.4k"), ("RNNN", "$14.8k"))),
)
MOCK_TIME = datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()


def mock_snapshot() -> dict:
    """Invent a coherent 48-token market without clients, caches or addresses."""
    symbols = ("ORBIT", "BMC", "RNNN", "NOVA", "MESH", "SPARK", "WAVE", "ECHO")
    tokens = []
    for index in range(48):
        known = index < 41
        price = round(.001 * (index + 1), 5) if known else None
        change = round(18.2 - index * .5, 1) if index < 22 else -(index - 21) if index < 36 else 0 if known else None
        volume = (38200, 21400, 14800, 2300)[index] if index < 4 else 1300 if known else None
        history = None
        if known:
            start = price / (1 + change / 100)
            history = [round(start + (price - start) * step / 23, 9) for step in range(24)]
        tokens.append(dict(
            id=f"mock:{index + 1}", launch_id=1200 - index,
            symbol=symbols[index] if index < len(symbols) else f"DEMO{index + 1}",
            name=f"Fictional token {index + 1}", chain=("eth", "base", "rh")[index % 3],
            launched_at=MOCK_TIME - ((.3, 2, 5, 12)[index] if index < 4 else 48 + index * 6) * 3600,
            price_usd=price, change_24h=change, volume_24h=volume,
            mcap_usd=price * 100_000_000 if known else None,
            buys_24h=100 + index if known else None, sells_24h=80 + index if known else None,
            paired_amount=4200 if index == 0 else 3.8 if index == 1 else 200 if index < 43 else None,
            paired_symbol="ETH" if index == 1 else "IMD",
            lp_state="two-sided" if index < 35 else "one-quote" if index < 43 else "unknown",
            sparkline=history, verdict="swarm", status="live",
        ))
    activity = [dict(id=f"mock-event:{index}", token_id=tokens[index]["id"],
                     ts=MOCK_TIME - index * 60, kind=kind, amount=amount, asset=asset)
                for index, (kind, amount, asset) in enumerate((
                    ("BUY", 42.6, "IMD"), ("SELL", .12, "ETH"), ("BUY", 66.8, "IMD"),
                    ("LAUNCH", None, ""), ("LP ADD", 18, "IMD")))]
    return dict(tokens=tokens, activity=activity, as_of=MOCK_TIME, is_mock=True)


MOCK_SNAPSHOT = mock_snapshot()


class SurfLaunchesHeroDemo(App):
    """Approved market overview above the existing LAUNCHES panels."""

    TITLE = "LAUNCHES / SWARM TOKENS — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #launches-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #launches-body { height: 1fr; min-height: 28; }
    #market-summary { height: 11; margin-bottom: 1; }
    #launches-body TokensTable { height: 1fr; min-height: 10; border: none; }
    #launches-body DataTable { height: 1fr; background: $background; scrollbar-size: 1 1; }
    #launches-body NewlyLaunched, #launches-body BestPlays, #launches-body TokenActivity {
        width: 1fr; height: 1fr; border: none; }
    #launches-body TokenActivity, #launches-body NewlyLaunched { margin-right: 1; }
    #launches-body .panel-title { height: 1; padding: 0 1; margin-bottom: 1; color: $text-muted;
        text-wrap: nowrap; text-overflow: ellipsis; }
    #launches-body RichLog { height: 1fr; padding: 0 1; background: $background; scrollbar-size: 1 1; }
    #launches-body #st-best-body { height: 1fr; padding: 0 1; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("LAUNCHES / SWARM TOKENS                                MOCK DATA · HERO PROPOSAL 1"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="launches-heroes")
                with Vertical(id="launches-body"):
                    with Horizontal(id="market-summary"):
                        yield TokenActivity()
                        yield NewlyLaunched()
                        yield BestPlays()
                    yield TokensTable()
        yield Static(Text("q quit · MOCK DATA · fictional market · 48 tokens · no API connection"), id="demo-footer")

    def on_mount(self):
        data = project_snapshot(MOCK_SNAPSHOT)
        self.query_one(TokenActivity).update_data(activity=data["activity"], tokens=data["tokens"])
        self.query_one(NewlyLaunched).update_data(newly_launched=data["newly_launched"], as_of=MOCK_TIME)
        self.query_one(BestPlays).update_data(gainers=data["gainers"], losers=data["losers"])
        self.query_one(TokensTable).update_data(tokens=data["tokens"], as_of=MOCK_TIME)
        self.query_one(DataTable).show_cursor = False


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfLaunchesHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="LAUNCHES / SWARM TOKENS · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfLaunchesHeroDemo().run()


if __name__ == "__main__":
    main()
