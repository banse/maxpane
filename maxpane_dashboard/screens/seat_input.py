"""Seat input screen -- prompts for an Identity.md (IDMD) seat number.

The surf AGENT body is about one seat of the swarm; a seat is an IDMD NFT, so
the number asked for is that NFT's token id.  The shape is THE LIST's wallet
prompt: validate, persist to ``~/.maxpane/config.toml``, dismiss with the value.
"""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Static

from maxpane_dashboard.config import get_seat, save_seat
from maxpane_dashboard.screens.wallet_input import SAVE_PATH_HINT, WalletInputScreen

#: A token id as typed: digits, optionally after a ``#`` (the hero prints
#: ``IDMD #1548``, so that is what gets copied).  ASCII digits only --
#: ``str.isdigit`` would admit ``١٥٤٨``, which ``int()`` then silently accepts.
_SEAT_RE = re.compile(r"#?([0-9]{1,10})")


def parse_seat(text: str) -> int | None:
    """The token id in ``text``, or ``None`` when it is not one."""
    match = _SEAT_RE.fullmatch(text.strip())
    return int(match.group(1)) if match else None


class SeatInputScreen(WalletInputScreen):
    """Prompts for an IDMD seat number and saves it.

    A subclass only to share ``WalletInputScreen``'s stylesheet: Textual's
    type selectors match base-class names, so the ``wi-*`` ids below are
    styled by the rules that already style the wallet prompt.
    """

    def compose(self) -> ComposeResult:
        current = get_seat()
        with Vertical(id="wi-wrap"):
            yield Static(
                "[bold]IDENTITY.MD SEAT[/]",
                id="wi-title",
                classes="wi-centered",
            )
            yield Static(
                "[dim]Enter your seat number (the Identity.md NFT id)[/]",
                id="wi-hint",
                classes="wi-centered",
            )
            # Disclosure before a durable write, as on the wallet prompt.
            yield Static(
                f"[dim]saved to {SAVE_PATH_HINT} · esc to cancel[/]",
                id="wi-save-note",
                classes="wi-centered",
            )
            yield Input(
                value="" if current is None else str(current),
                placeholder="e.g. 1548",
                restrict=r"#?[0-9]*",
                max_length=11,
                id="wi-input",
            )
            yield Static("", id="wi-error", classes="wi-centered")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Validate and save the seat number."""
        # Textual dispatches a handler on *every* class in the MRO: without
        # this, WalletInputScreen's own handler runs next and judges the seat
        # as a wallet address.
        event.prevent_default()
        error = self.query_one("#wi-error", Static)
        if not event.value.strip():
            error.update("[red]Please enter a seat number[/]")
            return
        token = parse_seat(event.value)
        if token is None:
            error.update("[red]Invalid seat — digits only, e.g. 1548[/]")
            return
        save_seat(token)
        self.dismiss(token)

    def on_key(self, event) -> None:
        """``escape`` cancels -- and the key ends here.

        Left to bubble, the same keypress reaches the surf screen's own
        ``escape`` binding once this prompt is gone and throws the reader out
        of the body they opened it from.
        """
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.dismiss(None)
