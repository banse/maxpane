"""Standalone LEADERBOARD proposal 1; every figure is fictional.

Run: .venv/bin/python scripts/surf_leaderboard_hero_demo.py
Export: add --export /tmp/surf-leaderboard-heroes.svg --size 149x45
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

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.swarm_fleet import SurfSwarmFleet
from maxpane_dashboard.widgets.surf.swarm_leaderboard import SurfSwarmLeaderboard
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()


def mock_snapshot() -> dict:
    """Build one coherent fictional record set and independent receipt totals."""
    rows = []
    other_seats = iter(range(1023))
    accepted_base, accepted_remainder = divmod(96000 - 4180, 1023)
    for index in range(1024):
        token = index + 1
        accepted = 4180 if token == 527 else accepted_base + (next(other_seats) < accepted_remainder)
        outcomes = {key: total // 1024 + (index < total % 1024)
                    for key, total in (("rejected", 2000), ("failed", 1000), ("pending", 1000))}
        attempts = accepted + sum(outcomes.values())
        rows.append(dict(
            token_id=token, accepted=accepted, attempts=attempts, accept_rate=accepted / attempts,
            **outcomes, devices=1, runtime="native", turns=580000 // 1024 + (index < 580000 % 1024),
            wall_clock_s=18000 * 3600 / 1024, working=int(index < 24),
            live_state="working" if index < 24 else "idle" if index < 966 else "offline",
        ))
    rows.sort(key=lambda row: (-row["accepted"], -row["accept_rate"], row["token_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    summary = {key: sum(row[key] for row in rows)
               for key in ("attempts", "accepted", "rejected", "failed", "pending", "turns", "working", "devices")}
    summary.update(
        seats=len(rows), live=sum(row["live_state"] != "offline" for row in rows), capacity=2880,
        receipts=18400, receipt_seats=1024, receipt_attempts=18400,
        receipt_accepted=17400, receipt_rejected=700, receipt_pending=300,
        wall_clock_ms=int(sum(row["wall_clock_s"] for row in rows) * 1000),
        input_tokens=420000000, output_tokens=80000000, tokens_per_completed_job=28400,
    )
    fleet = dict(
        runtimes=[dict(value="native", count=966)],
        models=[dict(model="gpt-6", effort="high", count=966)],
        daemons=[dict(value="v1", count=966)], os=[dict(value="linux", count=966)],
        profiles=[dict(value="worker", count=966)],
        concurrency=[dict(value="3", count=948), dict(value="2", count=18)],
        heartbeat_oldest_ts=MOCK_TIME - 30, heartbeat_newest_ts=MOCK_TIME, paused=[],
    )
    return dict(
        swarm_board_rows=rows, swarm_board_summary=summary, swarm_fleet=fleet,
        swarm_outcomes_source=dict(state="ok", read_ts=MOCK_TIME),
        swarm_workers_as_of_hhmm=hhmm(MOCK_TIME), swarm_contributors_as_of_hhmm=hhmm(MOCK_TIME),
    )


MOCK_DATA = mock_snapshot()
_SUMMARY = MOCK_DATA["swarm_board_summary"]
_TOP = MOCK_DATA["swarm_board_rows"][0]
MOCK_CARDS = (
    HeroRecord("top-seat", "TOP SEAT", "SEAT", f"RANK {_TOP['rank']}",
               digits=str(_TOP["token_id"]), subtitle=f"{_TOP['accepted'] / 1000:.2f}k accepted"),
    HeroRecord("recorded", "RECORDED", "RECORDS", "RECORDS", stats=(
        ("seats", f"{_SUMMARY['seats']:,}"), ("attempts", f"{_SUMMARY['attempts'] / 1000:.0f}k"))),
    HeroRecord("accept-rate", "ACCEPT RATE", "%", "ACCEPTED",
               digits=f"{_SUMMARY['accepted'] / _SUMMARY['attempts'] * 100:.1f}",
               subtitle=f"{_SUMMARY['accepted'] / 1000:.0f}k / {_SUMMARY['attempts'] / 1000:.0f}k"),
    HeroRecord("outcomes", "OUTCOMES", "RECORDS", "RECORDS", stats=tuple(
        (key, f"{_SUMMARY[key] / 1000:.0f}k") for key in ("rejected", "failed", "pending"))),
    HeroRecord("workers", "WORKERS", "NOW", "CURRENT", stats=tuple(
        (key, f"{_SUMMARY[key]:,}") for key in ("live", "working", "capacity"))),
    HeroRecord("effort", "EFFORT", "RECEIPTS", "CONTRIBUTORS", stats=(
        ("receipts", f"{_SUMMARY['receipts'] / 1000:.1f}k"),
        ("turns", f"{_SUMMARY['turns'] / 1000:.0f}k"),
        ("hours", f"{_SUMMARY['wall_clock_ms'] / 3600000 / 1000:.0f}k"))),
)


class SurfLeaderboardHeroDemo(App):
    TITLE = "LEADERBOARD / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #leaderboard-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #leaderboard-body { height: 1fr; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("LEADERBOARD / SURFBOARD                                MOCK DATA · HERO PROPOSAL 1"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="leaderboard-heroes")
                with Horizontal(id="leaderboard-body"):
                    yield SurfSwarmLeaderboard()
                    yield SurfSwarmFleet()
        yield Static(Text("q quit · MOCK DATA · fictional records, workers and receipts · no API connection"), id="demo-footer")

    def on_mount(self):
        for panel in (SurfSwarmLeaderboard, SurfSwarmFleet):
            self.query_one(panel).update_data(**MOCK_DATA)
        self.query_one(DataTable).show_cursor = False


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfLeaderboardHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="LEADERBOARD / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfLeaderboardHeroDemo().run()


if __name__ == "__main__":
    main()
