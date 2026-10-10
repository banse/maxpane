"""Offline preview: python -m maxpane_dashboard.demos.portfolio [--empty]."""
import argparse
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from maxpane_dashboard.copy_action import CopyAddressMixin
from maxpane_dashboard.explorer_action import ExplorerLinkMixin
from maxpane_dashboard.data.portfolio_demo import DemoPortfolioManager, SAMPLE_WALLET
from maxpane_dashboard.screens.portfolio import PortfolioScreen
from maxpane_dashboard.themes import THEMES


class PortfolioDemo(CopyAddressMixin, ExplorerLinkMixin, App):
    CSS_PATH = Path(__file__).parents[1] / 'themes' / 'minimal.tcss'
    BINDINGS = [Binding('q', 'quit', 'Quit')]

    def __init__(self, *, wallet=SAMPLE_WALLET):
        super().__init__()
        self.manager = DemoPortfolioManager(wallet)

    def on_mount(self):
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = 'matrix'
        self.push_screen(PortfolioScreen(self.manager, standalone=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty', action='store_true', help='Start with the wallet unset')
    args = parser.parse_args()
    PortfolioDemo(wallet=None if args.empty else SAMPLE_WALLET).run()
