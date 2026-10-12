"""Standalone LAUNCHPAD proposal 1; all figures and addresses are fictional.

Run: .venv/bin/python scripts/surf_launchpad_hero_demo.py
Export: add --export /tmp/surf-launchpad-heroes.svg --size 149x45
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

from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.burnkeepers import SurfBurnkeepers
from maxpane_dashboard.widgets.surf.launchpad import SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins
from maxpane_dashboard.widgets.surf.launchpad_activity import SurfLaunchpadActivity
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, NewsHeroCard
from scripts.surf_start_demo import parse_size


MOCK_TIME = datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp()
_USD_BUCKETS = (2800, 4100, 2500, 6200, 9800, 5600, 4300, 7300)
MOCK_VOLUME = dict(since=MOCK_TIME - 7200, until=MOCK_TIME, eth_usd=3200,
                   usd=_USD_BUCKETS, eth=tuple(value / 3200 for value in _USD_BUCKETS))


def mock_snapshot() -> dict:
    """One fictional snapshot; the native coin table is a top-twenty excerpt."""
    names = ('NOVA', 'ECHO', 'ALFA', 'BETA', 'GAMMA', 'WAVE', 'MESH', 'SPARK')
    coins = [dict(
        ticker=names[index] if index < len(names) else f'DEMO{index + 1}',
        name=f'Demo coin {index + 1}', creator=f'0x{index + 1:040x}', creator_known=False,
        age_s=(1080, 28800)[index] if index < 2 else (index + 1) * 86400,
        price_eth=.00001 * (index + 1), mcap_eth=200 + index * 10,
        mcap_usd=(200 + index * 10) * MOCK_VOLUME['eth_usd'],
        change_24h_pct=12.5 - index * 1.5, swaps_24h=240 - index * 11,
        swaps_all=600 - index * 20, imd_burned=500 - index * 20,
    ) for index in range(20)]
    activity = [dict(kind=kind, ticker=ticker, wallet=f'0x{1 if kind == "launch" else index + 1:040x}', wallet_known=False,
                     eth=eth, age_s=age)
                for index, (kind, ticker, eth, age) in enumerate((
                    ('buy', 'ALFA', .14, 120), ('sell', 'BETA', .08, 420),
                    ('launch', 'NOVA', None, 1080), ('buy', 'GAMMA', .22, 1500),
                    ('sell', 'WAVE', .06, 2100), ('buy', 'MESH', .12, 2700)))]
    keepers = [dict(wallet=f'0x{index + 100:040x}', wallet_known=False,
                    imd_burned=amount, eth_paid=.0012 + index * .0002, burns=10 - index * 3)
               for index, amount in enumerate((9000, 4200, 2500))]
    return dict(
        coin_count=210, launch_count=210, new_24h=2, creator_count=64,
        swap_count=12400, trader_count=486, creator_eth_owed=.0842,
        burn_accrued=250., burn_staged=120., burn_bridgeable=120., burn_ready=True,
        burn_min_bridge=100., burned_total=sum(row['imd_burned'] for row in keepers),
        as_of_hhmm='12:00', coins=coins, launchpad_activity=activity, launchpad_burnkeepers=keepers,
    )


MOCK_DATA = mock_snapshot()
MOCK_CARDS = (
    HeroRecord('coins', 'COINS', 'COINS', 'FACTORY', digits=str(MOCK_DATA['coin_count']),
               subtitle=f"{MOCK_DATA['new_24h']} new /24h"),
    HeroRecord('curve-flow', 'CURVE FLOW', 'HISTORY', 'OBSERVED', stats=(
        ('swaps', f"{MOCK_DATA['swap_count'] / 1000:.1f}k"),
        ('traders', str(MOCK_DATA['trader_count'])), ('creators', str(MOCK_DATA['creator_count'])))),
    HeroRecord('volume', 'VOLUME', 'kUSD', '2H',
               digits=f"{sum(MOCK_VOLUME['usd']) / 1000:.1f}", subtitle='2h to 12:00',
               points=tuple(MOCK_VOLUME['usd'])),
    HeroRecord('creator-fees', 'CREATOR FEES', 'ETH', 'UNCLAIMED',
               digits=f"{MOCK_DATA['creator_eth_owed']:.4f}", subtitle='owed'),
    HeroRecord('burn-queue', 'BURN QUEUE', 'IMD', 'READY' if MOCK_DATA['burn_ready'] else 'WAITING',
               stats=tuple((label, f"{MOCK_DATA[field]:.0f}") for label, field in (
                   ('accrued', 'burn_accrued'), ('staged', 'burn_staged'), ('sendable', 'burn_bridgeable')))),
    HeroRecord('burned', 'BURNED', 'kIMD', 'EVENT TOTAL',
               digits=f"{MOCK_DATA['burned_total'] / 1000:.1f}", subtitle='cumulative'),
)


class SurfLaunchpadHeroDemo(CopyAddressMixin, ExplorerLinkMixin, App):
    TITLE = 'LAUNCHPAD / SURFBOARD — MOCK DATA'
    CSS_PATH = Path(__file__).resolve().parent.parent / 'maxpane_dashboard/themes/minimal.tcss'
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding('q', 'quit', 'Quit', show=False)]
    CSS = """
    Screen { background: $background; color: $text; }
    #demo-title, #demo-footer { height: 1; padding: 0 1; background: $surface; color: $text-muted; }
    #viewport { height: 1fr; overflow: auto auto; scrollbar-size: 1 1; }
    #layout { height: 1fr; min-height: 41; min-width: 145; padding: 1 1; }
    #launchpad-heroes { height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1; margin-bottom: 1; }
    #launchpad-body { height: 1fr; }
    #launchpad-left { width: 2fr; height: 1fr; overflow-y: auto; scrollbar-size: 1 1; scrollbar-gutter: stable; }
    #launchpad-rail { width: 1fr; height: 1fr; overflow-y: auto; scrollbar-size: 1 1; scrollbar-gutter: stable; }
    #launchpad-body SurfLaunchpadCoins { width: 1fr; height: 2fr; min-height: 13; max-height: 23; padding: 0 1; margin-bottom: 1; }
    #launchpad-body SurfLaunchpadCoins > DataTable { height: auto; }
    #launchpad-body SurfLaunchpadActivity { width: 1fr; height: 1fr; min-height: 6; padding: 0 1; }
    #launchpad-body SurfCurveFlow, #launchpad-body SurfBurnPipeline { width: 1fr; height: auto; padding: 0 1; margin-bottom: 1; }
    #launchpad-body SurfBurnkeepers { width: 1fr; height: 1fr; min-height: 6; padding: 0 1; }
    """

    def __init__(self, cards=MOCK_CARDS):
        if len(cards) != 6:
            raise ValueError('the selected proposal requires exactly six cards')
        super().__init__()
        self.cards = cards
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'

    def compose(self) -> ComposeResult:
        yield Static(Text('LAUNCHPAD / SURFBOARD                                MOCK DATA · HERO PROPOSAL 1'), id='demo-title')
        with ScrollableContainer(id='viewport'):
            with Vertical(id='layout'):
                yield Grid(*(NewsHeroCard(card) for card in self.cards), id='launchpad-heroes')
                with Horizontal(id='launchpad-body'):
                    with Vertical(id='launchpad-left'):
                        yield SurfLaunchpadCoins()
                        yield SurfLaunchpadActivity()
                    with Vertical(id='launchpad-rail'):
                        yield SurfCurveFlow()
                        yield SurfBurnPipeline()
                        yield SurfBurnkeepers()
        yield Static(Text('q quit · MOCK DATA · fictional addresses · 2h volume at mock current ETH/USD · no API connection'), id='demo-footer')

    def on_mount(self):
        for panel in (SurfLaunchpadCoins, SurfLaunchpadActivity, SurfCurveFlow, SurfBurnPipeline, SurfBurnkeepers):
            self.query_one(panel).update_data(**MOCK_DATA)
        self.query_one(DataTable).show_cursor = False


async def export_demo(path: Path, size: tuple[int, int]):
    async with SurfLaunchpadHeroDemo().run_test(size=size) as pilot:
        await pilot.pause()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pilot.app.export_screenshot(title='LAUNCHPAD / SURFBOARD · MOCK DATA'))
        print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--export', type=Path, help='export an SVG instead of opening the mockup')
    parser.add_argument('--size', type=parse_size, default=(149, 45), help='export size (default: 149x45)')
    args = parser.parse_args()
    if args.export:
        asyncio.run(export_demo(args.export, args.size))
    else:
        SurfLaunchpadHeroDemo().run()


if __name__ == '__main__':
    main()
