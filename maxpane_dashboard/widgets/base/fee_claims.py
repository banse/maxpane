"""Fee claim event feed for the Base Terminal Fee Monitor view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static
from maxpane_dashboard.widgets.address import MIN_SHORT_COLS, short_hex
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: This panel shows a transaction hash, never a wallet or contract address --
#: outside the copy-icon rule (PRD §1: "Transaction hashes: Excluded"). It
#: still cannot keep a private slice-shaped shortener (E1 bans those
#: everywhere; PRD §3.2), so it shortens through ``short_hex`` like every
#: other 0x hex value in the repo -- deliberately with **no** icon.
#: ``MIN_SHORT_COLS`` is the narrowest window the helper allows; no wider
#: budget was worth spending on a value nobody clicks.
_TX_COLS = MIN_SHORT_COLS


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
    """Shorten a tx hash for display. No icon: transaction hashes are
    outside the copy-icon rule (PRD §1).

    ``short_hex`` returns a value that fails its own hex check **unchanged**
    -- unbounded length, unescaped -- because its job is windowing a real hex
    string, not sanitising an arbitrary one. This line is embedded directly
    into a ``markup=True`` RichLog line (CLAUDE.md: "Escape every third-party
    string before it reaches markup"), the same way ``token`` already is a
    few lines below, so the result is escaped here too.
    """
    if not tx_hash:
        return "--"
    return safe_markup(short_hex(tx_hash, _TX_COLS))


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
            token = safe_markup(f"{token:<12}")

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
                f"  [dim]{time_str}[/]  {token} {amount_str:>10}  "
                f"[dim]{tx_short}[/]{marker}"
            )
            log.write(line)
