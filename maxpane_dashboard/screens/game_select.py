"""Game selection screen shown after the splash."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Middle, Vertical
from textual.screen import Screen
from textual.widgets import Static


GAMES = [
    ("1", "surf", "Surfboard", "The onchain adventures of surfsurf.eth"),
    ("2", "fwa", "Fake World Assets", "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum"),
    ("3", "base", "Base Trading", "Trending tokens, volume, signals on Base"),
    ("4", "frenpet", "FrenPet", "Pet battles, leaderboard, activity on Base"),
    # Temporarily hidden — code intact, restore by uncommenting:
    # ("_", "frenpet_full", "FrenPet Full", "General, Wallet, Pet views on Base"),
    # ("_", "frenpet_wallet", "FrenPet Wallet", "ETH rewards, pool share, APR on Base"),
    # ("_", "frenpet_perf", "FrenPet Performance", "Pet comparison, velocity, win rates on Base"),
    ("5", "cattown", "Cat Town", "Fishing competition, KIBBLE economy on Base"),
    # Hidden — the game's backend is gone: wc2-agentic-dev-3o6un.ondigitalocean.app
    # is NXDOMAIN, so every fetch fails and the dashboard can only ever render its
    # unavailable state. Code and tests are intact (77 client tests); restore by
    # uncommenting here and re-adding "dota" to _GAME_CYCLE in app.py and to the
    # --game choices in __main__.py.
    # ("_", "dota", "DOTA", "Defense of the Agents idle MOBA on Base"),
    # Hidden on request. Both dashboards, their managers and their tests are
    # intact; restore by uncommenting here, re-adding the id to _GAME_CYCLE in
    # app.py and to the --game choices in __main__.py, and renumbering the keys
    # below so they stay contiguous (tests/test_cli_game_choices.py asserts it).
    # ("_", "bakery", "Rugpull Bakery", "Bake cookies, boost, attack on Abstract"),
    # ("_", "ocm", "OCM", "Onchain Monsters staking, supply, burns on Ethereum"),
    ("6", "ttt", "Ten Thousand Tokens", "NFT collection w/ UniV4 burn-to-launch on Ethereum"),
    ("7", "talismans", "Talismans", "Core-conservation NFT collection on Ethereum"),
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
        """Select a game by number.

        ``q`` is deliberately *not* handled here.  It used to call
        ``self.app.exit()``, which tears the app down without running
        ``MaxPaneApp.action_quit``: no manager's ``close()`` was awaited, so
        every ``httpx.AsyncClient`` was abandoned at event-loop teardown and
        ``save_cache()`` never ran -- quitting from the menu silently threw
        away the session's history, while quitting from a dashboard (which
        goes through the ``q`` binding) saved it.  Leaving the key unhandled
        lets it bubble to ``MaxPaneApp``'s ``q -> quit`` binding, so both
        quit paths run the same graceful shutdown (LOW-19).
        """
        for key, game_id, _name, _desc in GAMES:
            if event.character == key:
                self.dismiss(game_id)
                return
