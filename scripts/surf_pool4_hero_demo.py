"""Standalone POOL4 proposal 1; all figures and addresses are fictional.

Run: .venv/bin/python scripts/surf_pool4_hero_demo.py
Export: add --export /tmp/surf-pool4-heroes.svg --size 149x45
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

from maxpane_dashboard.analytics.surf_pool4_depth import MAX_TICK, band_distance_pct, eth_between
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.pool4_flow import SurfPool4Flow
from maxpane_dashboard.widgets.surf.pool4u_burn import SurfPool4UBurn
from maxpane_dashboard.widgets.surf.pool4u_depth import SurfPool4UDepth
from maxpane_dashboard.widgets.surf.pool4u_signals import SurfPool4USignals
from maxpane_dashboard.widgets.surf.pool4u_stakers import SurfPool4UStakers
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()


def mock_snapshot() -> dict:
    """A fixed fictional market, with one coherent vault and deployed band."""
    assets, rate, holders = 82400., 7.964, 126
    percentages = [18.2, 12., 8.] + [61.8 / (holders - 3)] * (holders - 3)
    stakers = [dict(rank=index + 1, address=f"0x{index + 1:040x}",
                    imd=assets * pct / 100, pct=pct)
               for index, pct in enumerate(percentages)]
    flow = [dict(ts=MOCK_TIME - age, age_s=age, side=side, size_imd=size,
                 burned_imd=burn, stakers_imd=reward, fee_imd=fee, fee_eth=0., settled=True)
            for age, side, size, burn, reward, fee in (
                (120, "buy", 120, 0, .8, 1.2), (480, "sell", 310, 31, 1.4, 3.1),
                (1260, "buy", 82, 0, .5, .82), (2100, "sell", 240, 24, 1.2, 2.4),
                (3300, "buy", 180, 0, 1.1, 1.8), (5400, "sell", 450, 45, 2.2, 4.5),
                (7200, "buy", 64, 0, .4, .64), (10800, "sell", 200, 20, 1., 2.),
            )]
    current_tick, band_tick = 57648, 57973
    # Match the native depth model's band inventory to the hero's ETH total.
    band_liquidity = 18.60 / eth_between(1., band_tick, MAX_TICK)
    return dict(
        pool4_price_usd=9.410, pool4_share_price=rate,
        pool4_venue_gap_pct=-1.20, pool4_cheaper_venue="here",
        pool4_vault_assets=assets, pool4_vault_shares=assets / rate,
        pool4_trailing_return_pct=8.4, pool4_staker_count=holders,
        pool4_stakers=stakers, pool4_staker_top3_pct=38.2,
        pool4_stakers_as_of_hhmm="12:00", pool4_stakers_state=None,
        pool4_current_tick=current_tick, pool4_reference_pool_tick=current_tick - 121,
        pool4_backstop_state="deployed", pool4_backstop_eth=18.60,
        pool4_backstop_lower_tick=band_tick, pool4_backstop_liquidity=band_liquidity,
        pool4_position_liquidity=1e21, pool4_cap_headroom=0.,
        pool4_backlog_imd=7440., pool4_drip_per_day=1200., pool4_backlog_days=6.2,
        pool4_flow=flow, pool4_total_burned=33279., pool4_total_supply=7080638.3,
        pool4_burned_supply_pct=.47, pool4_network="mainnet", pool4_as_of_hhmm="12:00",
    )


MOCK_DATA = mock_snapshot()
MOCK_CARDS = (
    HeroRecord("price", "IMD PRICE", "USD", "POOL4", "here -1.20%", digits="9.410"),
    HeroRecord("rate", "sIMD RATE", "IMD", "EXCHANGE", "per 1 sIMD", digits="7.964"),
    HeroRecord("staking", "STAKING", "APR %", "REALISED", "trailing 7d", digits="8.4"),
    HeroRecord("vault", "VAULT", "STATS", "STAKED",
               stats=(("IMD", "82.4k"), ("sIMD", "10.35k"), ("addresses", "126"))),
    HeroRecord("bid", "DOWNSIDE BID", "ETH", "DEPLOYED",
               f"{band_distance_pct(MOCK_DATA['pool4_current_tick'], MOCK_DATA['pool4_backstop_lower_tick']):.2f}% under",
               digits="18.60"),
    HeroRecord("queue", "DRIP QUEUE", "DELIVERY", "RATE LIMITED",
               stats=(("queued", "7.44k IMD"), ("cap", "1.2k IMD/d"), ("queue", "6.2d"))),
)


class SurfPool4HeroDemo(CopyAddressMixin, ExplorerLinkMixin, App):
    """The selected six-card mockup above the native market panels."""

    TITLE = "POOL4 / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #pool4-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #pool4-body { height: 1fr; min-height: 28; }
    #market-middle { height: 1fr; min-height: 14; margin-bottom: 1; }
    #market-middle SurfPool4Flow { width: 1fr; height: 1fr; }
    #market-rail { width: 1fr; height: 1fr; min-height: 14; }
    #market-rail SurfPool4UBurn { height: auto; padding: 0 1; margin-bottom: 1; }
    #market-rail SurfPool4USignals { height: 1fr; min-height: 6; padding: 0 1; }
    #market-bottom { height: 1fr; min-height: 12; }
    #market-bottom SurfPool4UStakers { width: 1fr; height: 1fr; padding: 0 1; }
    #market-bottom SurfPool4UDepth { width: 45; height: 1fr; padding: 0 1; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("POOL4 / SURFBOARD                                      MOCK DATA · HERO PROPOSAL 1"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="pool4-heroes")
                with Vertical(id="pool4-body"):
                    with Horizontal(id="market-middle"):
                        yield SurfPool4Flow(quiet_mainnet=True, quiet_as_of=True, classes="market")
                        with Vertical(id="market-rail"):
                            yield SurfPool4UBurn()
                            yield SurfPool4USignals()
                    with Horizontal(id="market-bottom"):
                        yield SurfPool4UStakers()
                        yield SurfPool4UDepth()
        yield Static(Text("q quit · MOCK DATA · fictional figures and addresses · no API connection"), id="demo-footer")

    def on_mount(self):
        for panel in (SurfPool4Flow, SurfPool4UBurn, SurfPool4USignals, SurfPool4UStakers, SurfPool4UDepth):
            self.query_one(panel).update_data(**MOCK_DATA)
        self.query_one(DataTable).show_cursor = False


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfPool4HeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="POOL4 / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfPool4HeroDemo().run()


if __name__ == "__main__":
    main()
