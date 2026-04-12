"""Game selection screen shown after the splash."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Middle, Vertical
from textual.screen import Screen
from textual.widgets import Static


GAMES = [
    ("1", "base", "Base Trading", "Trending tokens, volume, signals on Base"),
    ("2", "frenpet", "FrenPet", "Pet battles, leaderboard, activity on Base"),
    ("3", "cattown", "Cat Town", "Fishing competition, KIBBLE economy on Base"),
    ("4", "dota", "DOTA", "Defense of the Agents idle MOBA on Base"),
    ("5", "bakery", "Rugpull Bakery", "Bake cookies, boost, attack on Abstract"),
    ("6", "ocm", "OCM", "Onchain Monsters staking, supply, burns on Ethereum"),
]


class GameSelectScreen(Screen):
    """Minimal selection screen for choosing which dashboard to open."""

    DEFAULT_CSS = """
    GameSelectScreen {
        background: $background;
    }

    GameSelectScreen #gs-wrap {
        width: 1fr;
        height: auto;
        align: center middle;
    }

    GameSelectScreen #gs-title {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        margin-bottom: 2;
    }

    GameSelectScreen .gs-option {
        width: 100%;
        content-align: center middle;
        height: 3;
        margin: 0 0 1 0;
    }

    GameSelectScreen #gs-hint {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Middle():
            with Vertical(id="gs-wrap"):
                yield Static(
                    "[bold]CHOOSE PANE[/]",
                    id="gs-title",
                )
                for key, _game_id, name, desc in GAMES:
                    yield Static(
                        f"[bold $primary]\\[{key}][/]  [bold]{name}[/]  [dim]{desc}[/]",
                        classes="gs-option",
                    )
                yield Static(
                    "[dim]press number to select \u00b7 tab to cycle later \u00b7 q to quit[/]",
                    id="gs-hint",
                )

    def on_key(self, event) -> None:
        for key, game_id, _name, _desc in GAMES:
            if event.character == key:
                self.dismiss(game_id)
                return
        if event.character == "q":
            self.app.exit()
