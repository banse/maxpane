"""Standalone PROTOCOL proposal 1; all figures and addresses are fictional.

Run: .venv/bin/python scripts/surf_protocol_hero_demo.py
Export: add --export /tmp/surf-protocol-heroes.svg --size 149x45
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

from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from maxpane_dashboard.widgets.surf.pool4_hatches import SurfPool4Hatches
from maxpane_dashboard.widgets.surf.pool4_ratchet import SurfPool4Ratchet
from maxpane_dashboard.widgets.surf.pool4_split import SurfPool4Split
from maxpane_dashboard.widgets.surf.pool4_vault import SurfPool4Vault
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()


def mock_snapshot() -> dict:
    """One fixed fictional snapshot shared by the cards and native panels."""
    burned, fees = 33300., 3800.
    rewarded = burned * 15 / 85
    gross = burned + rewarded + fees
    cap, reserve, floor = 840000., 835000., 800000.
    assets, rate, queued, drip = 82400., 7.964, 7440., 1200.
    addresses = {name: f"0x{index:040x}" for index, name in enumerate(
        ("hook", "token", "vault", "distributor", "dripper"), start=1)}
    hatches = [dict(scope=scope, label=label, state=state, detail=detail, addr=None, addr_known=False)
               for scope, label, state, detail in (
                   ("vault", "owner", "renounced", "fictional deployment"),
                   ("vault", "paused", "live", "deposits enabled"),
                   ("vault", "rescue", "open", "stray tokens only"),
                   ("dripper", "owner", "live", "rate configurable"),
                   ("dripper", "rewards", "live", "vault delivery"),
                   ("distributor", "owner", "live", "allocation configurable"),
                   ("distributor", "rewards", "live", "staking via dripper"),
                   ("hook", "owner", "live", "parameters configurable"),
                   ("hook", "market", "open", "trading enabled"),
                   ("hook", "rebalance", "open", "backstop enabled"),
                   ("hook", "burn sink", "live", "burn executor"),
                   ("bond", "deployed", "live", "reserve allocation"),
               )]
    return dict(
        pool4_network="mainnet", pool4_as_of_hhmm="12:00",
        pool4_measured_inference_pct=fees / gross * 100,
        pool4_measured_burn_pct=burned / gross * 100,
        pool4_measured_stakers_pct=rewarded * .3 / gross * 100,
        pool4_reward_share_bps=1500, pool4_bps_denominator=10000, pool4_split_drift_bps=0.,
        pool4_total_burned=burned, pool4_total_rewarded=rewarded, pool4_total_fee_token=fees,
        pool4_retained_eth=0., pool4_last_claim_block=23500000,
        pool4_unsettled_burn=120., pool4_unsettled_stakers=120 * 15 / 85,
        pool4_counter_state="reconciled", pool4_counter_detail="fictional counters match event totals",
        pool4_reward_path="via-distributor",
        pool4_distributor_staking_bps=3000, pool4_distributor_nodes_bps=3000,
        pool4_distributor_bonding_bps=4000,
        pool4_distributor_staking_earned=rewarded * .3,
        pool4_distributor_nodes_earned=rewarded * .3, pool4_distributor_bonding_earned=rewarded * .4,
        pool4_distributor_held_nodes=rewarded * .3, pool4_distributor_held_bonding=rewarded * .4,
        pool4_tokens_in_pool=reserve, pool4_inventory_cap=cap, pool4_cap_headroom=cap - reserve,
        pool4_cap_floor=floor, pool4_floor_distance=reserve - floor,
        pool4_floor_distance_pct=(reserve - floor) / floor * 100, pool4_cap_decay_per_day=1200.,
        pool4_total_supply=7080000., pool4_burned_supply_pct=burned / 7080000 * 100,
        pool4_reserve_series=[(MOCK_TIME - age * 3600, reserve + age * 500) for age in range(12, -1, -1)],
        pool4_eth_in_pool=18.6, pool4_position_liquidity=1e21,
        pool4_current_tick=57648, pool4_ref_tick=57648, pool4_backstop_centred=True,
        pool4_share_price=rate, pool4_share_price_delta_pct=.12,
        pool4_vault_assets=assets, pool4_vault_shares=assets / rate,
        pool4_drip_per_day=drip, pool4_drippable=250., pool4_can_drip=True,
        pool4_backlog_imd=queued, pool4_backlog_days=queued / drip,
        pool4_implied_apr_pct=drip * 365 / assets * 100,
        pool4_hatches=hatches, pool4_discovery_state="adopted",
        pool4_discovery_detail="Fictional deployment for layout review",
        pool4_discovery_source="self-post", pool4_discovery_source_tx=f"0x{1:064x}",
        **{f"pool4_{name}_addr": address for name, address in addresses.items()},
    )


MOCK_DATA = mock_snapshot()
MOCK_CARDS = (
    HeroRecord("totals", "TOTALS", "IMD", "CUMULATIVE", stats=tuple(
        (label, f"{MOCK_DATA[key] / 1000:.1f}k") for label, key in (
            ("burned", "pool4_total_burned"), ("rewarded", "pool4_total_rewarded"), ("fees", "pool4_total_fee_token")))),
    HeroRecord("inventory", "INVENTORY", "IMD", "RATCHET", stats=tuple(
        (label, f"{MOCK_DATA[key] / 1000:.0f}k") for label, key in (
            ("cap", "pool4_inventory_cap"), ("reserve", "pool4_tokens_in_pool"), ("headroom", "pool4_cap_headroom")))),
    HeroRecord("split", "REWARD SPLIT", "REWARD %", "* DERIVED", stats=tuple(
        (label, f"{MOCK_DATA[f'pool4_distributor_{key}_bps'] / 100:.0f}%")
        for label, key in (("staking", "staking"), ("nodes", "nodes"), ("bonding*", "bonding")))),
    HeroRecord("unsettled", "UNSETTLED", "IMD", "PENDING", stats=tuple(
        (label, f"{MOCK_DATA[key]:.0f}") for label, key in (("burn", "pool4_unsettled_burn"), ("rewards", "pool4_unsettled_stakers")))),
    HeroRecord("delivery", "DELIVERY", "IMD", "RATE LIMITED", stats=(
        ("queued", f"{MOCK_DATA['pool4_backlog_imd'] / 1000:.2f}k"),
        ("ready", f"{MOCK_DATA['pool4_drippable']:.0f}"), ("cap", f"{MOCK_DATA['pool4_drip_per_day'] / 1000:.1f}k/d"))),
    HeroRecord("checks", "CHECKS", "STATUS", "ACCOUNTING", rows=(
        MOCK_DATA["pool4_counter_state"], f"drift {MOCK_DATA['pool4_split_drift_bps']:.1f} bps", "distributor")),
)


class SurfProtocolHeroDemo(CopyAddressMixin, ExplorerLinkMixin, App):
    TITLE = "PROTOCOL / SURFBOARD — MOCK DATA"
    CSS_PATH = Path(__file__).resolve().parent.parent / "maxpane_dashboard/themes/minimal.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("q", "quit", "Quit", show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: auto; min-height: 41; min-width: 145; padding: 1 1; }
    #protocol-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #protocol-body { height: auto; }
    .protocol-column { width: 1fr; height: auto; }
    SurfPool4Split, SurfPool4Hatches { margin-bottom: 1; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError("the selected proposal requires exactly six cards")
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"

    def compose(self) -> ComposeResult:
        yield Static(Text("PROTOCOL / SURFBOARD                                   MOCK DATA · HERO PROPOSAL 1"), id="demo-title")
        with ScrollableContainer(id="viewport"):
            with Vertical(id="layout"):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id="protocol-heroes")
                with Horizontal(id="protocol-body"):
                    with Vertical(classes="protocol-column"):
                        yield SurfPool4Split()
                        yield SurfPool4Ratchet()
                    with Vertical(classes="protocol-column"):
                        yield SurfPool4Hatches()
                        yield SurfPool4Vault()
        yield Static(Text("q quit · MOCK DATA · fictional figures and addresses · no API connection"), id="demo-footer")

    def on_mount(self):
        for panel in (SurfPool4Split, SurfPool4Ratchet, SurfPool4Hatches, SurfPool4Vault):
            self.query_one(panel).update_data(**MOCK_DATA)


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfProtocolHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title="PROTOCOL / SURFBOARD · MOCK DATA"))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="export an SVG instead of opening the mockup")
    parser.add_argument("--size", type=parse_size, default=(149, 45), help="export size (default: 149x45)")
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfProtocolHeroDemo().run()


if __name__ == "__main__":
    main()
