"""Run offline: python -m maxpane_dashboard.demos.swarm_tokens."""
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from maxpane_dashboard.data.swarm_tokens_demo import DemoSwarmTokensManager
from maxpane_dashboard.screens.swarm_tokens import SwarmTokensScreen
from maxpane_dashboard.themes import THEMES


class SwarmTokensDemo(App):
    CSS_PATH=Path(__file__).parents[1]/'themes'/'minimal.tcss'
    BINDINGS=[Binding('q','quit','Quit')]

    def on_mount(self):
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme='matrix'
        self.push_screen(SwarmTokensScreen(DemoSwarmTokensManager(), standalone=True))


if __name__=='__main__':
    SwarmTokensDemo().run()
