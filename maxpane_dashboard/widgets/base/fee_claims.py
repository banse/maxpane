"""Fee claim event feed for the Base Terminal Fee Monitor view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static


def _format_time(timestamp: float | int | str | None) -> str:
    """Convert a unix timestamp to HH:MM display format."""
    if timestamp is None:
        return "??:??"
    try:
        ts = float(timestamp)
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (ValueError, OSError):
        return "??:??"


def _short_tx(tx_hash: str | None) -> str:
    """Shorten a tx hash to 0xa3f2.. format."""
    if not tx_hash:
        return "--"
    if len(tx_hash) > 8:
        return f"{tx_hash[:6]}.."
    return tx_hash


class FeeClaims(Vertical):
    """RichLog showing fee claim events. Claims > 1 ETH get a BIG marker."""

    DEFAULT_CSS = """
    FeeClaims > .fc-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FeeClaims > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
        background: $background;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen_keys: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("FEE CLAIMS (live)", classes="fc-title")
        yield RichLog(id="fee-claims-log", wrap=True, highlight=True, markup=True)

    def on_mount(self) -> None:
        log = self.query_one("#fee-claims-log", RichLog)
        log.write("[dim]  Fee monitoring \u2014 connecting...[/]")

    def update_data(self, claims: list[dict] | None) -> None:
        """Append new fee claim events.

        Each claim dict expected keys:
            timestamp, token, amount_eth, tx_hash.
        """
        log = self.query_one("#fee-claims-log", RichLog)

        if not claims:
            return

        for claim in reversed(claims):
            ts = claim.get("timestamp")
            tx = claim.get("tx_hash", "")
            key = f"{ts}:{claim.get('token')}:{claim.get('amount_eth')}:{tx}"
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)

            time_str = _format_time(ts)
            token = claim.get("token", "???")
            if not token.startswith("$"):
                token = f"${token}"

            amount = claim.get("amount_eth", 0)
            try:
                amount_val = float(amount)
            except (ValueError, TypeError):
                amount_val = 0

            tx_short = _short_tx(tx)

            amount_str = f"{amount_val:.2f} ETH"

            # BIG marker for claims > 1 ETH
            if amount_val >= 1.0:
                marker = " [bold yellow]\u25cf BIG[/]"
                amount_str = f"[bold]{amount_str}[/]"
            else:
                marker = ""

            line = (
                f"  [dim]{time_str}[/]  {token:<12} {amount_str:>10}  "
                f"[dim]{tx_short}[/]{marker}"
            )
            log.write(line)
