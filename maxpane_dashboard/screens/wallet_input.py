"""Wallet input screen — prompts for an Ethereum wallet address."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Input, Static

from maxpane_dashboard.config import get_wallet, save_wallet


class WalletInputScreen(Screen):
    """Simple screen that prompts for a wallet address and saves it."""

    DEFAULT_CSS = """
    WalletInputScreen {
        background: $background;
        align: center middle;
    }

    WalletInputScreen #wi-wrap {
        width: 60;
        height: auto;
    }

    WalletInputScreen .wi-centered {
        width: 100%;
        content-align: center middle;
        text-align: center;
    }

    WalletInputScreen #wi-title {
        color: $text-muted;
        margin-bottom: 2;
    }

    WalletInputScreen #wi-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    WalletInputScreen #wi-error {
        color: red;
        margin-top: 1;
    }

    WalletInputScreen Input {
        width: 100%;
        margin: 1 0;
        border: none;
        padding: 0 1;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        current = get_wallet()
        with Vertical(id="wi-wrap"):
            yield Static(
                "[bold]WALLET ADDRESS[/]",
                id="wi-title",
                classes="wi-centered",
            )
            yield Static(
                "[dim]Enter your Ethereum wallet address (0x...)[/]",
                id="wi-hint",
                classes="wi-centered",
            )
            yield Input(
                value=current,
                placeholder="Paste wallet address here",
                id="wi-input",
            )
            yield Static("", id="wi-error", classes="wi-centered")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Validate and save the wallet address."""
        address = event.value.strip()
        error = self.query_one("#wi-error", Static)

        if not address:
            error.update("[red]Please enter a wallet address[/]")
            return

        if not address.startswith("0x") or len(address) != 42:
            error.update("[red]Invalid address — must be 0x followed by 40 hex characters[/]")
            return

        try:
            int(address[2:], 16)
        except ValueError:
            error.update("[red]Invalid hex characters in address[/]")
            return

        save_wallet(address)
        self.dismiss(address)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
