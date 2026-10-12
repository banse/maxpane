"""Standalone six-card ONCHAIN NEWS hero mockup; all records are fictional.

Run: .venv/bin/python scripts/surf_news_hero_demo.py
Export: add --export /tmp/surf-news-heroes.svg --size 149x45
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
from maxpane_dashboard.widgets.surf.activity import SurfDevActivity
from maxpane_dashboard.widgets.surf.feed import SurfFeed
from maxpane_dashboard.widgets.surf.market import SurfMarket
from maxpane_dashboard.widgets.surf.nft import SurfNft
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.signals import SurfSignals
from scripts.surf_start_demo import parse_size


MOCK_PRICE = (9.20, 9.22, 9.21, 9.27, 9.30, 9.28, 9.36, 9.41)
MOCK_POST = "Deploy agents to Robinhood from the swarm. Select a chain and launch with your existing seat."
MOCK_REPLY = "Can existing agents move over as well?"
MOCK_CARDS = (
    HeroRecord("announcement", "ANNOUNCEMENT", "LATEST", "OFFICIAL", "18m ago", preview=MOCK_POST),
    HeroRecord("reply", "LATEST REPLY", "COMMUNITY", "REPLY", "7m ago", preview=MOCK_REPLY, accent=False),
    HeroRecord("signals", "SIGNALS", "STATUS", "KNOWN 11/11",
               stats=(("fired", "2"), ("watch", "1"), ("quiet", "8")), accent=False),
    HeroRecord("activity", "DEV ACTIVITY", "RECENT", "RECENT", "2 wallets",
               rows=("6m  dev deploy", "21m ops bridge", "48m dev call")),
    HeroRecord("market", "IMD MARKET", "USD", "PRICE", "+2.3% · 24h", digits="9.41", points=MOCK_PRICE),
    HeroRecord("boards", "NFT BOARDS", "STATS", "IDENTITY.MD",
               stats=(("holders", "812"), ("written", "1,967"), ("24h moves", "38"))),
)

# Fixed demonstration snapshot; no clocks, clients, managers, or user settings.
MOCK_TIME = datetime(2026, 10, 12, 3, 30, tzinfo=timezone.utc).timestamp()
MOCK_FEED = (
    dict(ts=MOCK_TIME - 420, kind="reply", from_label="community", text=MOCK_REPLY, tx_hash=""),
    dict(ts=MOCK_TIME - 1080, kind="self", from_label="announce", text=MOCK_POST, tx_hash=""),
    dict(ts=MOCK_TIME - 7200, kind="self", from_label="announce",
         text="The agent dashboard now groups recent work by seat. Open a seat to inspect its record.", tx_hash=""),
    dict(ts=MOCK_TIME - 21600, kind="self", from_label="announce",
         text="Token pages show recent activity alongside the contract details and project links.", tx_hash=""),
)
MOCK_ACTIVITY = (
    dict(ts=MOCK_TIME - 360, wallet_label="dev", kind="deploy", counterparty="agent router", counterparty_known=True),
    dict(ts=MOCK_TIME - 1260, wallet_label="ops", kind="bridge", counterparty="IMD bridge", counterparty_known=True),
    dict(ts=MOCK_TIME - 2880, wallet_label="dev", kind="call", counterparty="launchpad", counterparty_known=True),
)
MOCK_SIGNALS = {f"sig_{name}_state": "ok" for name in
                ("post", "thread", "lp", "gate", "deploy", "bridge", "burn", "decoy", "burnready", "hot", "swarm")}
MOCK_SIGNALS.update(sig_post_state="fired", sig_post_age_s=1080, sig_post_detail="New chain rollout announced",
                    sig_deploy_state="fired", sig_deploy_age_s=360, sig_deploy_detail="New agent router deployed",
                    sig_bridge_state="watch", sig_bridge_detail="IMD staged for the bridge")
MOCK_MARKET = dict(
    imd_price_usd=9.41, imd_change_24h_pct=2.3, imd_vol_24h_usd=184200,
    pool_liquidity_usd=846000, fp_price_usd=9.38, parity_pct=0.32,
    supply_series=[(MOCK_TIME - (3 - index) * 3600, value)
                   for index, value in enumerate((4164500, 4164490, 4164480, 4164470))],
    price_series=[(MOCK_TIME - (7 - index) * 3600, value) for index, value in enumerate(MOCK_PRICE)],
    pool_id_source="hook")
MOCK_NFT = dict(nft_holders=812, nft_transfers_24h=38, nft_dev_holdings=24, nft_written=1967,
                nft_last_sales=[dict(ts=MOCK_TIME - 300, token_id=420, eth=0.042)])


class SurfNewsHeroDemo(App):
    """Native news panels below an isolated, mock-only hero design."""

    TITLE = "ONCHAIN NEWS / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #news-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #news-body { height: 1fr; min-height: 16; }
    #news-body SurfFeed { width: 7fr; padding: 0 1; }
    #news-rail { width: 6fr; height: 1fr; }
    #news-rail SurfSignals { height: auto; padding: 0 1; margin-bottom: 1; }
    #news-rail SurfDevActivity { height: 1fr; min-height: 7; padding: 0 1; }
    #context-bottom { height: 10; margin: 1 0 0 0; }
    #context-bottom SurfMarket { width: 7fr; height: 10; padding: 0 1; }
    #context-bottom SurfNft { width: 6fr; height: 10; padding: 0 1; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("ONCHAIN NEWS / SURFBOARD                                      MOCK DATA · HERO PROPOSAL 3"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="news-heroes")
                with Horizontal(id="news-body"):
                    yield SurfFeed()
                    with Vertical(id="news-rail"):
                        yield SurfSignals()
                        yield SurfDevActivity()
                with Horizontal(id="context-bottom"):
                    yield SurfMarket()
                    yield SurfNft()
        yield Static(Text("q quit · MOCK DATA · fictional announcements and figures · no API connection"), id="demo-footer")

    def on_mount(self):
        self.query_one(SurfFeed).update_data(feed_items=list(MOCK_FEED), feed_last_post_age_s=1080)
        self.query_one(SurfSignals).update_data(**MOCK_SIGNALS)
        self.query_one(SurfDevActivity).update_data(dev_activity=list(MOCK_ACTIVITY))
        self.query_one(SurfMarket).update_data(**MOCK_MARKET)
        self.query_one(SurfNft).update_data(**MOCK_NFT)


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfNewsHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="ONCHAIN NEWS / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfNewsHeroDemo().run()


if __name__ == "__main__":
    main()
